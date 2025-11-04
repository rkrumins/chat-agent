from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import uuid
from datetime import datetime
import asyncio
from enum import Enum
import logging
import json
import io
import re
from pathlib import Path
from typing import Literal

# Import production utilities
from utils import (
    validate_file_size, validate_content, validate_chunking_parameters,
    validate_chunk_quality, calculate_content_hash, detect_duplicate_content,
    sanitize_filename, estimate_processing_time, MAX_FILE_SIZE
)

# Import metadata extraction utilities
from metadata_extractor import (
    build_comprehensive_document_metadata,
    build_comprehensive_chunk_metadata
)

# File parsing imports
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VectorDB Management API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Initialize embedding function (MUST match chatbot's embedding model!)
# Using sentence-transformers model that chatbot uses
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# In-memory storage for processing status
processing_status: Dict[str, Dict[str, Any]] = {}

# Storage for content hashes (for duplicate detection)
# In production, this should be persisted (e.g., in a database)
content_hashes: Dict[str, List[str]] = {}  # collection_name -> list of hashes


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkingStrategy(str, Enum):
    """Chunking strategy options for document processing"""
    SEMANTIC = "semantic"  # Smart semantic chunking (default, best for most cases)
    SIZE = "size"  # Character-based chunking with size limit
    LINES = "lines"  # Line-based chunking (one line per chunk)
    PARAGRAPHS = "paragraphs"  # Paragraph-based chunking (paragraph separator)
    SENTENCES = "sentences"  # Sentence-based chunking (sentence boundaries)
    CUSTOM = "custom"  # Custom separator-based chunking


class DocumentMetadata(BaseModel):
    name: str
    purpose: Optional[str] = ""
    tags: Optional[str] = ""  # Comma-separated tags
    author: Optional[str] = None  # Document author/creator
    source: Optional[str] = None  # Source of the document (e.g., 'confluence', 'github', 'upload')
    custom_metadata: Optional[Dict[str, Any]] = {}


class DocumentCreate(BaseModel):
    collection_name: str
    metadata: DocumentMetadata
    content: Optional[str] = ""
    chunk_size: Optional[int] = 1000  # Increased default for better context
    chunk_overlap: Optional[int] = 200  # Increased default for better continuity
    chunking_strategy: Optional[str] = "semantic"  # Chunking strategy: semantic, size, lines, paragraphs, sentences, custom
    chunk_separator: Optional[str] = None  # Custom separator for chunking (used with custom strategy)
    max_chunks: Optional[int] = None  # Optional limit on total number of chunks
    create_new_version: Optional[bool] = False  # If True, create new version of existing doc


class DocumentUpdate(BaseModel):
    metadata: Optional[DocumentMetadata] = None
    content: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunking_strategy: Optional[str] = None
    chunk_separator: Optional[str] = None
    max_chunks: Optional[int] = None


class VersionInfo(BaseModel):
    version: int
    document_id: str
    created_at: str
    updated_by: Optional[str] = None
    change_notes: Optional[str] = None


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = {}


class DocumentResponse(BaseModel):
    id: str
    collection_name: str
    metadata: Dict[str, Any]
    content: str
    created_at: str
    updated_at: str


class ProcessingStatusResponse(BaseModel):
    task_id: str
    status: ProcessingStatus
    message: str
    progress: int
    created_at: str
    updated_at: str


# File parsing functions
def parse_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    if PdfReader is None:
        raise HTTPException(status_code=500, detail="PDF parsing not available. Install PyPDF2.")
    
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing PDF: {str(e)}")


def parse_docx(file_content: bytes) -> str:
    """Extract text from Word document"""
    if DocxDocument is None:
        raise HTTPException(status_code=500, detail="DOCX parsing not available. Install python-docx.")
    
    try:
        docx_file = io.BytesIO(file_content)
        doc = DocxDocument(docx_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing DOCX: {str(e)}")


def parse_txt(file_content: bytes) -> str:
    """Extract text from TXT file"""
    try:
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return file_content.decode('latin-1')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing TXT: {str(e)}")


def parse_json(file_content: bytes) -> str:
    """Extract text from JSON file"""
    try:
        data = json.loads(file_content.decode('utf-8'))
        # Convert JSON to readable text format
        return json.dumps(data, indent=2)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing JSON: {str(e)}")


def parse_file(filename: str, file_content: bytes) -> str:
    """Parse file based on extension"""
    extension = Path(filename).suffix.lower()
    
    parsers = {
        '.pdf': parse_pdf,
        '.docx': parse_docx,
        '.doc': parse_docx,
        '.txt': parse_txt,
        '.text': parse_txt,
        '.json': parse_json,
    }
    
    parser = parsers.get(extension)
    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}. Supported: PDF, DOCX, TXT, JSON"
        )
    
    return parser(file_content)


# Helper functions

def chunk_by_lines(text: str, max_chunks: Optional[int] = None) -> List[str]:
    """
    Chunk text by lines (one line per chunk).
    Useful for structured documents, code, or line-by-line data.
    This preserves all non-empty lines as separate chunks.
    """
    if not text or not text.strip():
        return []
    
    # Split by newlines (handles both \n and \r\n)
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    
    # Keep all non-empty lines (strip whitespace but keep the content)
    chunks = []
    for line in lines:
        stripped = line.strip()
        if stripped:  # Only include non-empty lines
            chunks.append(stripped)
    
    # Log for debugging large documents
    if len(chunks) > 50:
        logger.info(f"Line-based chunking: split {len(text.split())} words into {len(chunks)} line chunks")
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


def chunk_by_paragraphs(text: str, separator: str = '\n\n', chunk_size: int = 2000, overlap: int = 0, max_chunks: Optional[int] = None) -> List[str]:
    """
    Chunk text by paragraphs using a separator.
    If a paragraph exceeds chunk_size, it will be split by sentences.
    Useful for documents with clear paragraph structure.
    """
    paragraphs = text.split(separator)
    processed_chunks = []
    
    for para in paragraphs:
        trimmed = para.strip()
        if not trimmed:
            continue
        
        # If paragraph exceeds chunk_size, split it by sentences
        if len(trimmed) > chunk_size:
            # Split paragraph into sentences
            sentence_pattern = r'([.!?]+)\s+'
            sentences = re.split(sentence_pattern, trimmed)
            
            # Reconstruct sentences
            proper_sentences = []
            i = 0
            while i < len(sentences):
                if i + 1 < len(sentences) and re.match(sentence_pattern, sentences[i+1] + ' '):
                    proper_sentences.append(sentences[i] + sentences[i+1])
                    i += 2
                else:
                    if sentences[i].strip():
                        proper_sentences.append(sentences[i])
                    i += 1
            
            # Build chunks from sentences, respecting chunk_size
            current_chunk = []
            current_length = 0
            
            for sentence in proper_sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                sentence_length = len(sentence)
                
                if current_length + sentence_length + 1 > chunk_size and current_chunk:
                    processed_chunks.append(' '.join(current_chunk))
                    
                    if overlap > 0:
                        # Calculate overlap: keep last N sentences based on overlap size
                        overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                        current_chunk = overlap_sentences + [sentence]
                        current_length = len(' '.join(current_chunk))
                        
                        # Ensure overlap + new sentence doesn't exceed chunk_size (if it does, start fresh)
                        if current_length > chunk_size:
                            current_chunk = [sentence]
                            current_length = sentence_length
                    else:
                        current_chunk = [sentence]
                        current_length = sentence_length
                else:
                    current_chunk.append(sentence)
                    current_length += sentence_length + 1
                
                if max_chunks and len(processed_chunks) >= max_chunks:
                    break
            
            if current_chunk and (not max_chunks or len(processed_chunks) < max_chunks):
                processed_chunks.append(' '.join(current_chunk))
            
            if max_chunks and len(processed_chunks) >= max_chunks:
                break
        else:
            # Paragraph fits within chunk_size, use it as-is
            processed_chunks.append(trimmed)
            if max_chunks and len(processed_chunks) >= max_chunks:
                break
    
    chunks = processed_chunks
    
    # Add overlap between paragraph-based chunks (but ensure chunks don't exceed chunk_size)
    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            overlapped = chunk
            if i > 0:
                # Add overlap from previous chunk
                prev_chunk = chunks[i-1]
                max_overlap = min(overlap, len(prev_chunk))
                overlap_text = prev_chunk[-max_overlap:]
                combined_length = len(overlap_text) + len(separator) + len(chunk)
                
                # If adding overlap would exceed chunk_size, reduce the main chunk content
                if combined_length > chunk_size:
                    available_space = chunk_size - len(overlap_text) - len(separator)
                    if available_space > 0:
                        # Truncate the main chunk to make room for overlap
                        chunk = chunk[:available_space]
                        overlapped = f"{overlap_text}{separator}{chunk}"
                    else:
                        # If there's no room even after truncation, use minimal content
                        overlapped = f"{overlap_text}{separator}{chunk[:max(0, chunk_size - len(overlap_text) - len(separator))]}"
                else:
                    overlapped = f"{overlap_text}{separator}{chunk}"
            overlapped_chunks.append(overlapped)
        chunks = overlapped_chunks
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


def chunk_by_sentences(text: str, chunk_size: int = 1000, overlap: int = 200, max_chunks: Optional[int] = None) -> List[str]:
    """
    Chunk text by sentences, respecting chunk_size.
    Useful for maintaining sentence boundaries while controlling chunk size.
    """
    # Split by sentence endings
    sentence_pattern = r'([.!?]+)\s+'
    sentences = re.split(sentence_pattern, text)
    
    # Reconstruct sentences
    proper_sentences = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and re.match(sentence_pattern, sentences[i+1] + ' '):
            proper_sentences.append(sentences[i] + sentences[i+1])
            i += 2
        else:
            if sentences[i].strip():
                proper_sentences.append(sentences[i])
            i += 1
    
    # Build chunks from sentences
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in proper_sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        sentence_length = len(sentence)
        
        if current_length + sentence_length + 1 > chunk_size and current_chunk:
            chunks.append(' '.join(current_chunk))
            
            # Add overlap if specified
            if overlap > 0:
                # Calculate overlap: keep last N sentences based on overlap size
                overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                current_chunk = overlap_sentences + [sentence]
                current_length = len(' '.join(current_chunk))
                
                # Ensure overlap + new sentence doesn't exceed chunk_size (if it does, start fresh)
                if current_length > chunk_size:
                    current_chunk = [sentence]
                    current_length = sentence_length
            else:
                current_chunk = [sentence]
                current_length = sentence_length
        else:
            current_chunk.append(sentence)
            current_length += sentence_length + 1
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def chunk_by_size(text: str, chunk_size: int = 1000, overlap: int = 200, max_chunks: Optional[int] = None) -> List[str]:
    """
    Chunk text by character size with word boundaries.
    Simple character-based chunking that respects word boundaries.
    """
    if not text or not text.strip():
        return []
    
    if len(text) <= chunk_size:
        return [text.strip()]
    
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0
    
    for word in words:
        word_with_space = word + ' '
        word_length = len(word_with_space)
        
        if current_length + word_length > chunk_size and current_chunk:
            chunks.append(' '.join(current_chunk))
            
            # Add overlap
            if overlap > 0:
                # Calculate overlap: keep last N words based on overlap size
                overlap_words = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                current_chunk = overlap_words + [word]
                current_length = len(' '.join(current_chunk))
                
                # Ensure overlap + new word doesn't exceed chunk_size (if it does, start fresh)
                if current_length > chunk_size:
                    current_chunk = [word]
                    current_length = word_length
            else:
                current_chunk = [word]
                current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def chunk_by_custom_separator(text: str, separator: str, chunk_size: int = 1000, overlap: int = 0, max_chunks: Optional[int] = None) -> List[str]:
    """
    Chunk text using a custom separator.
    If chunks exceed chunk_size, they will be split further.
    Useful for structured data with known separators.
    """
    chunks = text.split(separator)
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    
    # If chunks exceed chunk_size, split them further
    if chunk_size:
        sized_chunks = []
        for chunk in chunks:
            if len(chunk) > chunk_size:
                # Split large chunks by words
                words = chunk.split()
                current_chunk = []
                current_length = 0
                
                for word in words:
                    word_with_space = word + ' '
                    word_length = len(word_with_space)
                    
                    if current_length + word_length > chunk_size and current_chunk:
                        sized_chunks.append(' '.join(current_chunk))
                        
                        if overlap > 0:
                            overlap_words = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                            current_chunk = overlap_words + [word]
                            current_length = len(' '.join(current_chunk))
                            
                            # Ensure overlap + new word doesn't exceed chunk_size (if it does, start fresh)
                            if current_length > chunk_size:
                                current_chunk = [word]
                                current_length = word_length
                        else:
                            current_chunk = [word]
                            current_length = word_length
                    else:
                        current_chunk.append(word)
                        current_length += word_length
                    
                    if max_chunks and len(sized_chunks) >= max_chunks:
                        break
                
                if current_chunk and (not max_chunks or len(sized_chunks) < max_chunks):
                    sized_chunks.append(' '.join(current_chunk))
                
                if max_chunks and len(sized_chunks) >= max_chunks:
                    break
            else:
                sized_chunks.append(chunk)
                if max_chunks and len(sized_chunks) >= max_chunks:
                    break
        chunks = sized_chunks
    
    # Add overlap if specified (but ensure chunks don't exceed chunk_size)
    if overlap > 0 and len(chunks) > 1:
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            overlapped = chunk
            if i > 0:
                prev_chunk = chunks[i-1]
                max_overlap = min(overlap, len(prev_chunk))
                overlap_text = prev_chunk[-max_overlap:]
                
                if chunk_size:
                    combined_length = len(overlap_text) + len(separator) + len(chunk)
                    if combined_length > chunk_size:
                        available_space = chunk_size - len(overlap_text) - len(separator)
                        if available_space > 0:
                            chunk = chunk[:available_space]
                            overlapped = f"{overlap_text}{separator}{chunk}"
                        else:
                            overlapped = f"{overlap_text}{separator}{chunk[:max(0, chunk_size - len(overlap_text) - len(separator))]}"
                    else:
                        overlapped = f"{overlap_text}{separator}{chunk}"
                else:
                    overlapped = f"{overlap_text}{separator}{chunk}"
            overlapped_chunks.append(overlapped)
        chunks = overlapped_chunks
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


def chunk_text(
    text: str, 
    chunk_size: int = 1000, 
    overlap: int = 200,
    strategy: str = "semantic",
    separator: Optional[str] = None,
    max_chunks: Optional[int] = None
) -> List[str]:
    """
    Advanced chunking function with multiple strategies.
    Supports semantic, size-based, line-based, paragraph-based, sentence-based, and custom separator chunking.
    
    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters (for size, sentences, semantic strategies)
                   Not used for "lines" strategy
        overlap: Overlap size in characters or elements (default 200)
                Not used for "lines" strategy
        strategy: Chunking strategy - "semantic", "size", "lines", "paragraphs", "sentences", "custom"
        separator: Custom separator for "custom" strategy (or override for paragraphs)
                  Required for "custom" strategy, optional for "paragraphs" (defaults to '\n\n')
        max_chunks: Optional limit on total number of chunks (applies to all strategies)
    
    Returns:
        List of text chunks based on the specified strategy
    """
    if not text or not text.strip():
        return []
    
    # Normalize strategy name
    strategy = strategy.lower() if strategy else "semantic"
    
    # Ensure chunk_size and overlap are valid (sanitize if needed)
    if chunk_size is None or chunk_size < 0:
        chunk_size = 1000
    if overlap is None or overlap < 0:
        overlap = 200
    
    # Route to appropriate chunking strategy
    try:
        if strategy == "lines":
            # Lines strategy: one line per chunk, ignores chunk_size and overlap
            return chunk_by_lines(text, max_chunks)
        
        elif strategy == "paragraphs":
            # Paragraphs strategy: split by separator (default '\n\n'), respects chunk_size and overlap
            sep = separator if separator else '\n\n'
            return chunk_by_paragraphs(text, separator=sep, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
        
        elif strategy == "sentences":
            # Sentences strategy: split by sentence boundaries, respects chunk_size and overlap
            return chunk_by_sentences(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
        
        elif strategy == "size":
            # Size strategy: split by character size with word boundaries, respects chunk_size and overlap
            return chunk_by_size(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
        
        elif strategy == "custom":
            # Custom strategy: split by custom separator, respects chunk_size and overlap
            if not separator or separator.strip() == "":
                # Fallback to paragraphs if no separator provided
                logger.warning("Custom separator strategy used without separator, falling back to paragraph separator '\\n\\n'")
                separator = '\n\n'
            return chunk_by_custom_separator(text, separator=separator, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
        
        else:
            # Default: semantic chunking (smart chunking with Mix-of-Granularity)
            logger.info(f"Unknown strategy '{strategy}', using semantic chunking")
            return chunk_text_semantic(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    
    except Exception as e:
        logger.error(f"Error in chunk_text with strategy '{strategy}': {str(e)}")
        # Fallback to semantic chunking on error
        logger.warning(f"Falling back to semantic chunking due to error")
        return chunk_text_semantic(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)


def chunk_text_semantic(text: str, chunk_size: int = 1000, overlap: int = 200, max_chunks: Optional[int] = None) -> List[str]:
    """
    Advanced semantic chunking with Mix-of-Granularity approach:
    Split text into overlapping chunks using sentence and paragraph boundaries for better context preservation.
    This follows RAG best practices for semantic coherence and is optimized for large-scale document processing.
    
    Mix-of-Granularity (MoG) features:
    - Dynamic chunk sizing based on content structure (paragraphs, sentences, sections)
    - Respects paragraph boundaries for semantic coherence
    - Uses sentence boundaries to avoid cutting mid-thought
    - Intelligent overlap that preserves context across chunks
    - Handles various text structures (paragraphs, lists, code blocks, definitions)
    - Optimized for both large books (100s of pages) and small definitions (millions of entries)
    
    For large-scale ingestion (100s of books, millions of definitions):
    - Smaller chunks (500-1000 chars) for definitions: better precision
    - Larger chunks (1000-2000 chars) for books: better context
    - Adaptive sizing based on document type detected
    
    Args:
        text: Text to chunk
        chunk_size: Target chunk size in characters (default 1000 for better context)
                   For definitions, use 500-800. For books, use 1000-2000.
        overlap: Overlap size in characters (default 200 for context continuity)
                Typically 10-20% of chunk_size for optimal results
        max_chunks: Optional limit on total number of chunks
    
    Returns:
        List of text chunks with semantic coherence preserved
    """
    if not text or not text.strip():
        return []
    
    # If text is smaller than chunk_size, return as single chunk
    if len(text) <= chunk_size:
        result = [text.strip()]
        if max_chunks:
            result = result[:max_chunks]
        return result
    
    chunks = []
    
    # Split text into sentences (handles multiple sentence endings)
    # Pattern matches: . ! ? followed by space or newline
    sentence_pattern = r'([.!?]+)\s+'
    sentences = re.split(sentence_pattern, text)
    
    # Reconstruct sentences (split includes delimiters)
    proper_sentences = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences) and re.match(sentence_pattern, sentences[i+1] + ' '):
            proper_sentences.append(sentences[i] + sentences[i+1])
            i += 2
        else:
            if sentences[i].strip():
                proper_sentences.append(sentences[i])
            i += 1
    
    # Fallback: if sentence splitting fails or text has no sentence markers,
    # split by paragraph breaks or fall back to character-based with word boundaries
    if len(proper_sentences) == 0 or len(proper_sentences[0]) > chunk_size:
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        proper_sentences = []
        for para in paragraphs:
            if len(para.strip()) > chunk_size:
                # If paragraph is too long, split by sentences within it
                para_sentences = re.split(r'([.!?]+)\s+', para)
                j = 0
                while j < len(para_sentences):
                    if j + 1 < len(para_sentences) and re.match(r'([.!?]+)', para_sentences[j+1]):
                        proper_sentences.append(para_sentences[j] + para_sentences[j+1])
                        j += 2
                    else:
                        if para_sentences[j].strip():
                            proper_sentences.append(para_sentences[j])
                        j += 1
            else:
                if para.strip():
                    proper_sentences.append(para)
    
    # If still no good splits, use word boundaries
    if len(proper_sentences) == 0 or (len(proper_sentences) == 1 and len(proper_sentences[0]) > chunk_size * 2):
        # Split by words and respect chunk boundaries
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_with_space = word + ' '
            word_length = len(word_with_space)
            
            if current_length + word_length > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                # Start overlap: take last N words for overlap
                if overlap > 0:
                    overlap_words = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                    current_chunk = overlap_words + [word]
                    current_length = len(' '.join(current_chunk))
                    
                    # Ensure overlap + new word doesn't exceed chunk_size (if it does, start fresh)
                    if current_length > chunk_size:
                        current_chunk = [word]
                        current_length = word_length
                else:
                    current_chunk = [word]
                    current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length
            
            # Check max_chunks limit
            if max_chunks and len(chunks) >= max_chunks:
                break
        
        if current_chunk and (not max_chunks or len(chunks) < max_chunks):
            chunks.append(' '.join(current_chunk))
        
        result = [chunk.strip() for chunk in chunks if chunk.strip()]
        if max_chunks:
            result = result[:max_chunks]
        return result
    
    # Build chunks from sentences
    current_chunk = []
    current_length = 0
    
    for sentence in proper_sentences:
        # Check max_chunks limit
        if max_chunks and len(chunks) >= max_chunks:
            break
        
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_length = len(sentence)
        
        # If single sentence exceeds chunk size, add it anyway and split later if needed
        if sentence_length > chunk_size:
            # Save current chunk if it has content
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            
            # Split the long sentence by word boundaries
            words = sentence.split()
            temp_chunk = []
            temp_length = 0
            
            for word in words:
                word_with_space = word + ' '
                if temp_length + len(word_with_space) > chunk_size and temp_chunk:
                    chunks.append(' '.join(temp_chunk))
                    if max_chunks and len(chunks) >= max_chunks:
                        break
                    temp_chunk = [word]
                    temp_length = len(word)
                else:
                    temp_chunk.append(word)
                    temp_length += len(word_with_space)
            
            if temp_chunk:
                current_chunk = temp_chunk
                current_length = temp_length
            else:
                current_chunk = []
                current_length = 0
        else:
            # Check if adding this sentence would exceed chunk size
            if current_length + sentence_length + 1 > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                if max_chunks and len(chunks) >= max_chunks:
                    break
                
                # Create overlap: include last few sentences from current chunk
                if overlap > 0:
                    overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                    current_chunk = overlap_sentences + [sentence]
                    current_length = len(' '.join(current_chunk))
                    
                    # Ensure overlap + new sentence doesn't exceed chunk_size (if it does, start fresh)
                    if current_length > chunk_size:
                        current_chunk = [sentence]
                        current_length = sentence_length
                else:
                    current_chunk = [sentence]
                    current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length + 1  # +1 for space
    
    # Add final chunk
    if current_chunk and (not max_chunks or len(chunks) < max_chunks):
        chunks.append(' '.join(current_chunk))
    
    result = [chunk.strip() for chunk in chunks if chunk.strip()]
    if max_chunks:
        result = result[:max_chunks]
    return result


def prepare_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare metadata for ChromaDB - convert lists to strings"""
    chroma_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, list):
            # Convert list to comma-separated string
            chroma_metadata[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            # Convert dict to JSON string
            chroma_metadata[key] = json.dumps(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            chroma_metadata[key] = value
        else:
            # Convert other types to string
            chroma_metadata[key] = str(value)
    return chroma_metadata


def get_next_version_number(collection, document_name: str) -> int:
    """Get the next version number for a document name"""
    try:
        all_docs = collection.get(include=["metadatas"])
        max_version = 0
        
        for i, doc_id in enumerate(all_docs["ids"]):
            doc_metadata = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
            if (doc_metadata.get("name") == document_name and 
                doc_metadata.get("is_chunk") is False):
                version = doc_metadata.get("version", 1)
                max_version = max(max_version, version)
        
        return max_version + 1
    except:
        return 1


def detect_document_type(content: str, metadata: Dict[str, Any]) -> str:
    """
    Detect document type based on content and metadata.
    Returns: 'book', 'definition', 'article', 'blog_post', 'poem', or 'unknown'
    """
    doc_name = metadata.get("name", "").lower()
    purpose = metadata.get("purpose", "").lower()
    tags = metadata.get("tags", "").lower()
    
    # Check metadata first
    if any(word in doc_name or word in purpose or word in tags 
           for word in ["definition", "definitions", "glossary", "dictionary"]):
        return "definition"
    if any(word in doc_name or word in purpose or word in tags 
           for word in ["book", "textbook", "guide", "manual", "tome"]):
        return "book"
    if any(word in doc_name or word in purpose or word in tags 
           for word in ["article", "paper", "essay"]):
        return "article"
    if any(word in doc_name or word in purpose or word in tags 
           for word in ["blog", "post", "entry"]):
        return "blog_post"
    if any(word in doc_name or word in purpose or word in tags 
           for word in ["poem", "poetry", "verse", "sonnet"]):
        return "poem"
    
    # Content-based detection
    content_lower = content[:2000].lower()  # Check first 2000 chars
    
    # Poem indicators: line breaks, rhyme patterns, verse structure
    lines = content.split('\n')
    avg_line_length = sum(len(line.strip()) for line in lines[:20]) / max(1, min(20, len(lines)))
    if avg_line_length < 50 and len(lines) > 5:
        if any(word in content_lower for word in ["verse", "stanza", "rhyme", "poem"]):
            return "poem"
    
    # Definition indicators: term-definition patterns
    definition_patterns = [
        r'^[A-Z][a-z]+:\s*[A-Z]',  # Term: Definition
        r'^[A-Z][a-z]+\s+—\s+',     # Term — Definition
        r'^[A-Z][a-z]+\s+=\s+',     # Term = Definition
    ]
    definition_count = sum(1 for line in lines[:50] 
                          if any(re.match(pattern, line.strip()) for pattern in definition_patterns))
    if definition_count > 5:
        return "definition"
    
    # Article indicators: structured sections, citations
    if any(word in content_lower for word in ["abstract", "introduction", "conclusion", "references", "citation"]):
        return "article"
    
    # Blog post indicators: casual tone, dates, tags
    if any(word in content_lower for word in ["posted on", "published", "tags:", "#", "read more"]):
        return "blog_post"
    
    # Book indicators: chapters, table of contents, comprehensive structure
    if any(word in content_lower for word in ["chapter", "table of contents", "preface", "appendix"]):
        return "book"
    
    # Default: if it's substantial content (>5000 chars), likely a book
    if len(content) > 5000:
        return "book"
    
    return "unknown"


def create_contextual_chunk(chunk_text: str, document_name: str, document_type: str, 
                            chunk_number: int, total_chunks: int, metadata: Dict[str, Any]) -> str:
    """
    Create contextual chunk by prepending document type, name, and context.
    This improves retrieval accuracy by ensuring embeddings include document type information.
    """
    # Create contextual prefix
    context_parts = []
    
    # Document type indicator (critical for filtering)
    doc_type_map = {
        "book": "BOOK",
        "definition": "DEFINITION",
        "article": "ARTICLE", 
        "blog_post": "BLOG_POST",
        "poem": "POEM",
        "unknown": "DOCUMENT"
    }
    type_label = doc_type_map.get(document_type, "DOCUMENT")
    context_parts.append(f"[DOCUMENT_TYPE: {type_label}]")
    
    # Document name
    context_parts.append(f"[DOCUMENT_NAME: {document_name}]")
    
    # Chunk position (for context)
    if total_chunks > 1:
        context_parts.append(f"[CHUNK: {chunk_number} of {total_chunks}]")
    
    # Purpose/tags if available (helpful for retrieval)
    purpose = metadata.get("purpose", "")
    tags = metadata.get("tags", "")
    if purpose:
        context_parts.append(f"[PURPOSE: {purpose[:100]}]")  # Limit length
    if tags:
        context_parts.append(f"[TAGS: {tags[:100]}]")
    
    # Build contextual chunk
    context_header = " ".join(context_parts)
    contextual_chunk = f"{context_header}\n\n{chunk_text}"
    
    return contextual_chunk


def mark_previous_versions_as_old(collection, document_name: str):
    """Mark all previous versions of a document as not latest"""
    try:
        all_docs = collection.get(include=["metadatas"])
        
        for i, doc_id in enumerate(all_docs["ids"]):
            doc_metadata = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
            if (doc_metadata.get("name") == document_name and 
                doc_metadata.get("is_chunk") is False and
                doc_metadata.get("is_latest") is True):
                # Update metadata to mark as not latest
                doc_metadata["is_latest"] = False
                # Note: ChromaDB doesn't support in-place metadata updates easily
                # This is a limitation we'll document
                logger.info(f"Document {doc_id} is now an old version")
    except Exception as e:
        logger.warning(f"Error marking old versions: {str(e)}")


async def process_document_async(
    task_id: str,
    collection_name: str,
    document_id: str,
    content: str,
    metadata: Dict[str, Any],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    chunking_strategy: str = "semantic",
    chunk_separator: Optional[str] = None,
    max_chunks: Optional[int] = None,
    version: int = 1,
    max_retries: int = 3
):
    """Process document asynchronously with status updates, validation, and error recovery"""
    retry_count = 0
    last_error = None
    
    while retry_count <= max_retries:
        try:
            # Update status
            processing_status[task_id]["status"] = ProcessingStatus.PROCESSING
            processing_status[task_id]["message"] = "Validating document content..." if retry_count == 0 else f"Retrying (attempt {retry_count + 1}/{max_retries + 1})..."
            processing_status[task_id]["progress"] = 5
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Step 1: Validate content
            is_valid, error_msg, sanitized_content = validate_content(content)
            if not is_valid:
                raise ValueError(f"Content validation failed: {error_msg}")
            
            content = sanitized_content  # Use sanitized content
            
            # Step 2: Validate chunking parameters
            is_valid, error_msg = validate_chunking_parameters(
                chunk_size, chunk_overlap, chunking_strategy, max_chunks
            )
            if not is_valid:
                raise ValueError(f"Chunking parameter validation failed: {error_msg}")
            
            # Step 3: Check for duplicates (optional - can be disabled in metadata)
            check_duplicates = metadata.get("check_duplicates", True)
            if check_duplicates:
                processing_status[task_id]["message"] = "Checking for duplicates..."
                processing_status[task_id]["progress"] = 10
                processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                
                existing_hashes = content_hashes.get(collection_name, [])
                is_duplicate, hash_value = detect_duplicate_content(content, existing_hashes)
                
                if is_duplicate:
                    logger.warning(f"Duplicate content detected for document {document_id} (hash: {hash_value[:16]}...)")
                    # Allow duplicates but log them - in production you might want to skip or warn
                    processing_status[task_id]["message"] = "Warning: Duplicate content detected, proceeding anyway..."
                else:
                    # Store hash for future duplicate detection
                    if collection_name not in content_hashes:
                        content_hashes[collection_name] = []
                    content_hashes[collection_name].append(hash_value)
            
            # Step 4: Estimate processing time
            processing_status[task_id]["message"] = "Estimating processing time..."
            processing_status[task_id]["progress"] = 15
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            time_estimate = estimate_processing_time(len(content), chunk_size)
            processing_status[task_id]["estimated_time"] = time_estimate.get("estimated_total_time", 0)
            processing_status[task_id]["estimated_chunks"] = time_estimate.get("estimated_chunks", 0)
            
            # Step 5: Chunk document
            processing_status[task_id]["message"] = "Chunking document..."
            processing_status[task_id]["progress"] = 20
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Use chunking strategy from metadata or parameters
            strategy = metadata.get("chunking_strategy") or chunking_strategy or "semantic"
            separator = metadata.get("chunk_separator") or chunk_separator
            max_chunks_param = metadata.get("max_chunks") or max_chunks
            
            # Log chunking parameters for debugging
            logger.info(f"Chunking with strategy='{strategy}', chunk_size={chunk_size}, "
                       f"chunk_overlap={chunk_overlap}, separator={separator}, max_chunks={max_chunks_param}")
            logger.info(f"Document content length: {len(content)} characters, {len(content.split())} words")
            
            chunks = chunk_text(
                content, 
                chunk_size=chunk_size, 
                overlap=chunk_overlap,
                strategy=strategy,
                separator=separator,
                max_chunks=max_chunks_param
            )
            
            logger.info(f"Initial chunking produced {len(chunks)} chunks using strategy '{strategy}'")
            
            # Step 6: Validate chunk quality
            processing_status[task_id]["message"] = "Validating chunk quality..."
            processing_status[task_id]["progress"] = 40
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # For line-based chunking, use more lenient validation (don't filter small chunks)
            # because each line might be a valid definition even if short
            use_strict_validation = strategy.lower() != "lines"
            valid_chunks, quality_metrics = validate_chunk_quality(chunks, strict_min_size=use_strict_validation)
            
            # Store quality metrics in processing status
            processing_status[task_id]["quality_metrics"] = quality_metrics
            
            # Check if we have any valid chunks
            if len(valid_chunks) == 0:
                raise ValueError("No valid chunks generated after quality validation. " + 
                               "; ".join(quality_metrics.get("issues", ["Unknown error"])))
            
            # Warn if many chunks were filtered (but less strict for lines strategy)
            if quality_metrics["filtered_chunks"] > 0:
                if strategy.lower() == "lines" and quality_metrics["filtered_chunks"] > len(chunks) * 0.5:
                    # If more than 50% filtered for lines strategy, something is wrong
                    logger.warning(f"Filtered {quality_metrics['filtered_chunks']} chunks using lines strategy. "
                                 f"Valid chunks: {quality_metrics['valid_chunks']}/{quality_metrics['total_chunks']}")
                elif strategy.lower() != "lines":
                    logger.warning(f"Filtered {quality_metrics['filtered_chunks']} invalid chunks. "
                                 f"Valid chunks: {quality_metrics['valid_chunks']}/{quality_metrics['total_chunks']}")
            
            chunks = valid_chunks  # Use validated chunks
            
            # Log chunk count for debugging
            logger.info(f"Chunking strategy '{strategy}' produced {len(chunks)} chunks from document")
            
            processing_status[task_id]["message"] = f"Processing {len(chunks)} validated chunks..."
            processing_status[task_id]["progress"] = 50
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Step 7: Get or create collection
            processing_status[task_id]["message"] = "Preparing vector database collection..."
            processing_status[task_id]["progress"] = 55
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            collection = chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"description": metadata.get("description", "")},
                embedding_function=embedding_function
            )
            
            # Step 8: Detect document type
            processing_status[task_id]["message"] = "Detecting document type and creating contextual chunks..."
            processing_status[task_id]["progress"] = 60
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Detect document type
            document_type = detect_document_type(content, metadata)
            logger.info(f"Detected document type: {document_type} for document: {metadata.get('name', 'Unknown')}")
            
            # Adaptive chunk sizing based on document type (Mix-of-Granularity approach)
            # Only applies to semantic strategy - user-specified strategies use exact parameters
            if strategy.lower() == "semantic":
                # This optimizes for large-scale processing: smaller chunks for definitions, larger for books
                adaptive_chunk_size = chunk_size
                adaptive_overlap = chunk_overlap
                
                if document_type == "definition":
                    # Definitions benefit from smaller, precise chunks for better retrieval accuracy
                    adaptive_chunk_size = min(800, max(500, chunk_size))
                    adaptive_overlap = min(150, max(50, chunk_overlap))
                elif document_type == "book":
                    # Books benefit from larger chunks to preserve context and reduce chunk count
                    adaptive_chunk_size = max(1000, min(2000, chunk_size))
                    adaptive_overlap = max(200, min(400, chunk_overlap))
                elif document_type == "article":
                    # Articles use medium chunks
                    adaptive_chunk_size = max(800, min(1500, chunk_size))
                    adaptive_overlap = max(150, min(300, chunk_overlap))
                
                # Use adaptive sizes for chunking
                if adaptive_chunk_size != chunk_size or adaptive_overlap != chunk_overlap:
                    logger.info(f"Adaptive chunking (semantic): {document_type} -> size={adaptive_chunk_size}, overlap={adaptive_overlap}")
                    chunk_size = adaptive_chunk_size
                    chunk_overlap = adaptive_overlap
        
            # Step 9: Prepare comprehensive metadata for ChromaDB
            processing_status[task_id]["message"] = "Preparing comprehensive metadata..."
            processing_status[task_id]["progress"] = 70
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Add chunking parameters to metadata for document
            metadata["chunk_size"] = chunk_size
            metadata["chunk_overlap"] = chunk_overlap
            metadata["chunking_strategy"] = strategy
            metadata["chunk_separator"] = separator
            metadata["max_chunks"] = max_chunks_param
            metadata["chunk_count"] = len(chunks)
            metadata["quality_metrics"] = quality_metrics
            
            # Build comprehensive document metadata following RAG best practices
            document_metadata = build_comprehensive_document_metadata(
                document_id=document_id,
                name=metadata.get("name", "Unknown"),
                metadata=metadata,
                collection_name=collection_name,
                document_type=document_type,
                content=content,
                version=version
            )
            
            # Prepare for ChromaDB (convert lists/dicts to strings)
            chroma_metadata = prepare_metadata_for_chroma(document_metadata)
            
            # Step 10: Store chunks in vector database
            processing_status[task_id]["message"] = "Storing in vector database with contextual chunks..."
            processing_status[task_id]["progress"] = 80
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Store chunks with enhanced metadata and contextual prefixes
            # Always store chunks, even if there's only one, for consistency
            if len(chunks) >= 1:
                chunk_ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
                contextual_chunks = []
                chunk_metadata_list = []
                
                document_name = metadata.get("name", "Unknown")
                
                # For large documents, process in batches to avoid memory issues
                batch_size = 100  # Process 100 chunks at a time
                total_chunks = len(chunks)
                
                logger.info(f"Processing {total_chunks} chunks in batches of {batch_size}")
                
                for i, chunk in enumerate(chunks):
                    # Update progress for large documents
                    if total_chunks > 50 and i % 50 == 0:
                        progress = 80 + int((i / total_chunks) * 10)  # 80-90% range
                        processing_status[task_id]["progress"] = progress
                        processing_status[task_id]["message"] = f"Processing chunks {i+1}/{total_chunks}..."
                        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                    
                    # Create contextual chunk with document type and metadata prepended
                    contextual_chunk = create_contextual_chunk(
                        chunk_text=chunk,
                        document_name=document_name,
                        document_type=document_type,
                        chunk_number=i + 1,
                        total_chunks=total_chunks,
                        metadata=metadata
                    )
                    contextual_chunks.append(contextual_chunk)
                    
                    # Build comprehensive chunk metadata following RAG best practices
                    # Note: For large documents, we don't pass full document_content to avoid memory issues
                    # Only pass a small sample for page estimation
                    previous_chunk = chunks[i - 1] if i > 0 else None
                    content_sample = content[:5000] if len(content) > 5000 else content  # Sample for page estimation
                    
                    try:
                        chunk_meta = build_comprehensive_chunk_metadata(
                            chunk_id=chunk_ids[i],
                            chunk_index=i,
                            chunk_text=chunk,
                            document_metadata=document_metadata,
                            document_content=content_sample,  # Use sample instead of full content
                            previous_chunk_text=previous_chunk,
                            total_chunks=total_chunks
                        )
                    except Exception as e:
                        logger.warning(f"Error building metadata for chunk {i}: {str(e)}, using minimal metadata")
                        # Fallback to minimal metadata if extraction fails
                        chunk_meta = {
                            "chunk_id": chunk_ids[i],
                            "chunk_index": i,
                            "chunk_number": i + 1,
                            "parent_id": document_id,
                            "document_id": document_id,
                            "document_name": document_name,
                            "document_type": document_type,
                            "total_chunks": total_chunks,
                            "is_chunk": True,
                            "chunk_position": f"{i + 1} of {total_chunks}"
                        }
                    
                    # Prepare for ChromaDB (convert lists/dicts to strings)
                    chunk_meta_processed = prepare_metadata_for_chroma(chunk_meta)
                    chunk_metadata_list.append(chunk_meta_processed)
                
                # Add contextual chunks to collection in batches for large documents
                # ChromaDB can handle large batches, but we batch to provide progress updates
                if total_chunks > batch_size:
                    logger.info(f"Storing {total_chunks} chunks in batches of {batch_size}")
                    for batch_start in range(0, total_chunks, batch_size):
                        batch_end = min(batch_start + batch_size, total_chunks)
                        batch_ids = chunk_ids[batch_start:batch_end]
                        batch_docs = contextual_chunks[batch_start:batch_end]
                        batch_meta = chunk_metadata_list[batch_start:batch_end]
                        
                        collection.add(
                            documents=batch_docs,
                            metadatas=batch_meta,
                            ids=batch_ids
                        )
                        
                        # Update progress
                        progress = 80 + int((batch_end / total_chunks) * 10)
                        processing_status[task_id]["progress"] = progress
                        processing_status[task_id]["message"] = f"Stored chunks {batch_start+1}-{batch_end}/{total_chunks}..."
                        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                        
                        logger.info(f"Stored batch {batch_start//batch_size + 1}: chunks {batch_start+1}-{batch_end}")
                else:
                    # Single batch for smaller documents
                    collection.add(
                        documents=contextual_chunks,
                        metadatas=chunk_metadata_list,
                        ids=chunk_ids
                    )
                
                logger.info(f"Stored {total_chunks} contextual chunks for document type: {document_type}")
            
            # Step 11: Store full document
            processing_status[task_id]["message"] = "Storing document with comprehensive metadata..."
            processing_status[task_id]["progress"] = 90
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Update timestamp
            chroma_metadata["updated_at"] = datetime.utcnow().isoformat()
            chroma_metadata["is_chunk"] = False
            
            # Full document metadata is already comprehensive from build_comprehensive_document_metadata
            full_doc_metadata = chroma_metadata
            
            collection.add(
                documents=[content],
                metadatas=[full_doc_metadata],
                ids=[document_id]
            )
            
            # Step 12: Success!
            processing_status[task_id]["status"] = ProcessingStatus.COMPLETED
            processing_status[task_id]["message"] = f"Document processed successfully. {len(chunks)} chunks stored."
            processing_status[task_id]["progress"] = 100
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            processing_status[task_id]["chunk_count"] = len(chunks)
            
            logger.info(f"Document {document_id} processed successfully with {len(chunks)} chunks")
            break  # Success - exit retry loop
            
        except ValueError as e:
            # Validation errors should not be retried
            logger.error(f"Validation error processing document {document_id}: {str(e)}")
            processing_status[task_id]["status"] = ProcessingStatus.FAILED
            processing_status[task_id]["message"] = f"Validation error: {str(e)}"
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            break  # Don't retry validation errors
            
        except Exception as e:
            last_error = str(e)
            retry_count += 1
            
            if retry_count <= max_retries:
                # Exponential backoff for retries
                wait_time = min(2 ** retry_count, 30)  # Max 30 seconds
                logger.warning(f"Error processing document {document_id} (attempt {retry_count}/{max_retries + 1}): {str(e)}. Retrying in {wait_time}s...")
                processing_status[task_id]["message"] = f"Error occurred, retrying in {wait_time}s... (attempt {retry_count}/{max_retries + 1})"
                processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                await asyncio.sleep(wait_time)
            else:
                # Max retries reached
                logger.error(f"Error processing document {document_id} after {max_retries + 1} attempts: {last_error}")
                processing_status[task_id]["status"] = ProcessingStatus.FAILED
                processing_status[task_id]["message"] = f"Failed after {max_retries + 1} attempts: {last_error}"
                processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                processing_status[task_id]["error"] = last_error


# API Endpoints

@app.get("/")
async def root():
    return {
        "message": "VectorDB Management API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check ChromaDB connection
        collections = chroma_client.list_collections()
        
        return {
            "status": "healthy",
            "chromadb": "connected",
            "collections_count": len(collections),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Collection endpoints

@app.get("/collections")
async def list_collections():
    """List all collections"""
    try:
        collections = chroma_client.list_collections()
        result_collections = []
        
        for col in collections:
            # Get only non-chunk documents for accurate count
            try:
                all_docs = col.get(include=["metadatas"])
                doc_count = sum(1 for i, _ in enumerate(all_docs["ids"]) 
                              if all_docs["metadatas"][i].get("is_chunk") is False)
            except:
                doc_count = col.count()  # Fallback to total count
            
            result_collections.append({
                "name": col.name,
                "id": col.id,
                "metadata": col.metadata,
                "count": doc_count
            })
        
        return {"collections": result_collections}
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections")
async def create_collection(collection: CollectionCreate):
    """Create a new collection"""
    try:
        col = chroma_client.create_collection(
            name=collection.name,
            metadata={
                "description": collection.description,
                **collection.metadata,
                "created_at": datetime.utcnow().isoformat()
            },
            embedding_function=embedding_function
        )
        return {
            "name": col.name,
            "id": col.id,
            "metadata": col.metadata,
            "message": "Collection created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating collection: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete a collection"""
    try:
        chroma_client.delete_collection(name=collection_name)
        return {"message": f"Collection '{collection_name}' deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting collection: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))


# Document endpoints

@app.get("/collections/{collection_name}/documents")
async def list_documents(
    collection_name: str, 
    skip: int = 0, 
    limit: int = 100,
    show_all_versions: bool = False
):
    """List all documents in a collection (latest versions by default)"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get all non-chunk documents
        all_results = collection.get(include=["documents", "metadatas"])
        
        documents = []
        
        # First pass: collect all documents
        doc_ids_to_process = []
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Skip chunks (handle both boolean and string)
            is_chunk = metadata.get("is_chunk")
            is_chunk_bool = is_chunk is True or str(is_chunk).lower() == "true"
            if is_chunk_bool:
                continue
            
            # Skip old versions unless requested
            if not show_all_versions and metadata.get("is_latest") is False:
                continue
            
            doc_ids_to_process.append((doc_id, i))
        
        # Second pass: count chunks for each document
        # Build a map of chunk counts by document_id
        chunk_counts = {}
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            is_chunk = metadata.get("is_chunk")
            # Handle both boolean True and string "True" cases
            is_chunk_bool = is_chunk is True or str(is_chunk).lower() == "true"
            if is_chunk_bool:
                parent_id = metadata.get("parent_id") or metadata.get("document_id")
                if parent_id:
                    chunk_counts[parent_id] = chunk_counts.get(parent_id, 0) + 1
        
        # Third pass: build document list with accurate chunk counts
        for doc_id, idx in doc_ids_to_process:
            metadata = all_results["metadatas"][idx] if all_results["metadatas"] else {}
            content = all_results["documents"][idx] if all_results["documents"] else ""
            
            # Use stored chunk_count if available, otherwise count dynamically
            chunk_count = metadata.get("chunk_count")
            if chunk_count is None or chunk_count == 0:
                chunk_count = chunk_counts.get(doc_id, 0)
            
            # Update metadata with accurate chunk_count
            if chunk_count > 0:
                metadata["chunk_count"] = chunk_count
            
            # Ensure chunk_size and chunk_overlap are integers (ChromaDB may store as strings)
            # Also ensure they exist - if not present, don't add defaults here (let frontend handle it)
            if "chunk_size" in metadata and metadata["chunk_size"] is not None:
                try:
                    metadata["chunk_size"] = int(metadata["chunk_size"])
                except (ValueError, TypeError):
                    # If conversion fails, try to get from string
                    try:
                        metadata["chunk_size"] = int(str(metadata["chunk_size"]).strip())
                    except (ValueError, TypeError):
                        pass  # Keep original value if conversion fails
            if "chunk_overlap" in metadata and metadata["chunk_overlap"] is not None:
                try:
                    metadata["chunk_overlap"] = int(metadata["chunk_overlap"])
                except (ValueError, TypeError):
                    # If conversion fails, try to get from string
                    try:
                        metadata["chunk_overlap"] = int(str(metadata["chunk_overlap"]).strip())
                    except (ValueError, TypeError):
                        pass  # Keep original value if conversion fails
            
            # Debug: Log if chunk_size/chunk_overlap are missing (for troubleshooting)
            # Only log once per document to avoid spam
            if "chunk_size" not in metadata or metadata.get("chunk_size") is None:
                logger.debug(f"Document {doc_id} missing chunk_size in metadata")
            if "chunk_overlap" not in metadata or metadata.get("chunk_overlap") is None:
                logger.debug(f"Document {doc_id} missing chunk_overlap in metadata")
            
            documents.append({
                "id": doc_id,
                "collection_name": collection_name,
                "metadata": metadata,
                "content": content,
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "version": metadata.get("version", 1)
            })
        
        # Sort by updated_at descending
        documents.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        # Apply pagination
        paginated_docs = documents[skip:skip+limit]
        
        return {
            "documents": paginated_docs,
            "total": len(documents),
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}")
async def get_document(collection_name: str, document_id: str):
    """Get a specific document"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        result = collection.get(
            ids=[document_id],
            include=["documents", "metadatas"]
        )
        
        if not result["ids"]:
            raise HTTPException(status_code=404, detail="Document not found")
        
        metadata = result["metadatas"][0] if result["metadatas"] else {}
        content = result["documents"][0] if result["documents"] else ""
        
        return {
            "id": document_id,
            "collection_name": collection_name,
            "metadata": metadata,
            "content": content,
            "created_at": metadata.get("created_at", ""),
            "updated_at": metadata.get("updated_at", "")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}/chunks")
async def get_document_chunks(collection_name: str, document_id: str, skip: int = 0, limit: int = 100):
    """Get all chunks for a specific document with metadata"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get all documents to find chunks (ids are returned by default)
        all_results = collection.get(include=["documents", "metadatas"])
        
        chunks = []
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Check if this is a chunk belonging to the requested document
            # Check both parent_id and document_id fields, and ensure is_chunk is True
            parent_id = metadata.get("parent_id") or metadata.get("document_id")
            is_chunk = metadata.get("is_chunk")
            
            # Handle both boolean True and string "True" cases
            is_chunk_bool = is_chunk is True or str(is_chunk).lower() == "true"
            
            if parent_id == document_id and is_chunk_bool:
                
                content = all_results["documents"][i] if all_results["documents"] else ""
                
                # Clean up contextual prefixes for display
                display_content = content
                if "[DOCUMENT_TYPE:" in display_content:
                    lines = display_content.split("\n\n")
                    if len(lines) > 1:
                        display_content = "\n\n".join(lines[1:])
                
                # Get chunk index and total chunks for accurate position
                chunk_index = metadata.get("chunk_index", 0)
                total_chunks = len(chunks) + 1  # Will be updated after we count all chunks
                
                chunk_data = {
                    "id": doc_id,
                    "chunk_index": chunk_index,
                    "chunk_number": metadata.get("chunk_number", chunk_index + 1),
                    "content": display_content,
                    "raw_content": content,  # Keep original for reference
                    "metadata": metadata,
                    "length": len(content),
                    "word_count": metadata.get("word_count", len(content.split())),
                    "content_type": metadata.get("content_type", "paragraph"),
                    "topics": metadata.get("topics", ""),
                    "difficulty_level": metadata.get("difficulty_level", "Intermediate"),
                    "section_title": metadata.get("section_title", ""),
                    "chunk_position": metadata.get("chunk_position", ""),  # Will be recalculated below
                }
                chunks.append(chunk_data)
        
        # Sort by chunk index
        chunks.sort(key=lambda x: x.get("chunk_index", 0))
        
        # Recalculate chunk_position with accurate total count (after we have all chunks)
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk_index = chunk.get("chunk_index", 0)
            chunk["chunk_position"] = f"{chunk_index + 1} of {total_chunks}"
        
        # Apply pagination
        total = len(chunks)
        paginated_chunks = chunks[skip:skip+limit]
        
        return {
            "chunks": paginated_chunks,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document chunks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents")
async def create_document(
    collection_name: str,
    document: DocumentCreate,
    background_tasks: BackgroundTasks
):
    """Create a new document from text with validation"""
    try:
        # Step 1: Validate and sanitize content
        is_valid, error_msg, sanitized_content = validate_content(document.content or "")
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Content validation failed: {error_msg}")
        
        # Step 2: Validate chunking parameters
        is_valid, error_msg = validate_chunking_parameters(
            document.chunk_size or 1000,
            document.chunk_overlap or 200,
            document.chunking_strategy or "semantic",
            document.max_chunks
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Use sanitized content
        document.content = sanitized_content
        
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Check if creating a new version
        version = 1
        if document.create_new_version:
            version = get_next_version_number(collection, document.metadata.name)
            mark_previous_versions_as_old(collection, document.metadata.name)
        
        document_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Initialize processing status
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Prepare metadata with enhanced fields
        metadata = {
            "name": document.metadata.name,
            "purpose": document.metadata.purpose or "",
            "tags": document.metadata.tags or "",
            "author": document.metadata.author,
            "source": document.metadata.source,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **document.metadata.custom_metadata
        }
        
        # Queue background processing
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            document.content,
            metadata,
            document.chunk_size,
            document.chunk_overlap,
            document.chunking_strategy or "semantic",
            document.chunk_separator,
            document.max_chunks,
            version
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": version,
            "message": f"Document queued for processing (version {version})",
            "status": ProcessingStatus.PENDING
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    collection_name: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    purpose: str = Form(""),
    tags: str = Form(""),
    author: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    chunking_strategy: str = Form("semantic"),
    chunk_separator: Optional[str] = Form(None),
    max_chunks: Optional[int] = Form(None),
    custom_metadata: str = Form("{}"),
    create_new_version: bool = Form(False)
):
    """Upload and process a document file with validation"""
    try:
        # Step 1: Validate file size
        file_content = await file.read()
        file_size = len(file_content)
        
        is_valid, error_msg = validate_file_size(file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Step 2: Sanitize filename
        sanitized_filename = sanitize_filename(file.filename)
        
        # Step 3: Parse file based on type
        try:
            content = parse_file(sanitized_filename, file_content)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing file: {str(e)}")
        
        # Step 4: Validate and sanitize content
        is_valid, error_msg, sanitized_content = validate_content(content)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Content validation failed: {error_msg}")
        
        content = sanitized_content
        
        # Step 5: Validate chunking parameters
        is_valid, error_msg = validate_chunking_parameters(
            chunk_size, chunk_overlap, chunking_strategy, max_chunks
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Check if creating a new version
        version = 1
        if create_new_version:
            version = get_next_version_number(collection, name)
            mark_previous_versions_as_old(collection, name)
        
        document_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Initialize processing status
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Parse custom metadata
        try:
            custom_meta = json.loads(custom_metadata) if custom_metadata else {}
        except json.JSONDecodeError:
            custom_meta = {}
        
        # Prepare metadata with enhanced fields
        metadata = {
            "name": name,
            "purpose": purpose or "",
            "tags": tags or "",
            "author": author or None,
            "source": source or None,
            "filename": sanitized_filename,
            "original_filename": file.filename,
            "file_type": Path(sanitized_filename).suffix.lower(),
            "file_size": file_size,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **custom_meta
        }
        
        # Queue background processing
        # Convert max_chunks to int if provided
        max_chunks_int = None
        if max_chunks is not None:
            try:
                max_chunks_int = int(max_chunks) if max_chunks != "null" and max_chunks != "" else None
            except (ValueError, TypeError):
                max_chunks_int = None
        
        # Store chunking parameters in metadata
        metadata["chunking_strategy"] = chunking_strategy or "semantic"
        if chunk_separator:
            metadata["chunk_separator"] = chunk_separator
        if max_chunks_int:
            metadata["max_chunks"] = max_chunks_int
        
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            content,
            metadata,
            chunk_size,
            chunk_overlap,
            chunking_strategy or "semantic",
            chunk_separator if chunk_separator and chunk_separator != "null" else None,
            max_chunks_int,
            version
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": version,
            "message": f"Document queued for processing (version {version})",
            "status": ProcessingStatus.PENDING,
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/collections/{collection_name}/documents/{document_id}")
async def update_document(
    collection_name: str,
    document_id: str,
    update: DocumentUpdate,
    background_tasks: BackgroundTasks
):
    """Update an existing document"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get existing document
        existing = collection.get(
            ids=[document_id],
            include=["documents", "metadatas"]
        )
        
        if not existing["ids"]:
            raise HTTPException(status_code=404, detail="Document not found")
        
        existing_metadata = existing["metadatas"][0]
        existing_content = existing["documents"][0]
        
        # Prepare updated metadata
        updated_metadata = existing_metadata.copy()
        
        if update.metadata:
            updated_metadata.update({
                "name": update.metadata.name,
                "purpose": update.metadata.purpose or "",
                "tags": update.metadata.tags or "",
                **update.metadata.custom_metadata
            })
        
        updated_metadata["updated_at"] = datetime.utcnow().isoformat()
        
        # Use updated content or keep existing
        updated_content = update.content if update.content else existing_content
        
        # Get chunk parameters - use update values if provided, otherwise fall back to existing metadata
        chunk_size = update.chunk_size if update.chunk_size is not None else existing_metadata.get("chunk_size", 1000)
        chunk_overlap = update.chunk_overlap if update.chunk_overlap is not None else existing_metadata.get("chunk_overlap", 200)
        chunking_strategy = update.chunking_strategy if update.chunking_strategy else existing_metadata.get("chunking_strategy", "semantic")
        chunk_separator = update.chunk_separator if update.chunk_separator is not None else existing_metadata.get("chunk_separator")
        max_chunks = update.max_chunks if update.max_chunks is not None else existing_metadata.get("max_chunks")
        
        # Store chunking parameters in metadata for future reference
        updated_metadata["chunk_size"] = chunk_size
        updated_metadata["chunk_overlap"] = chunk_overlap
        updated_metadata["chunking_strategy"] = chunking_strategy
        if chunk_separator:
            updated_metadata["chunk_separator"] = chunk_separator
        if max_chunks:
            updated_metadata["max_chunks"] = max_chunks
        
        # Delete old chunks
        try:
            # Get all documents to find chunks manually
            all_results = collection.get(include=["metadatas"])
            chunk_ids_to_delete = []
            
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                if metadata.get("parent_id") == document_id and metadata.get("is_chunk") is True:
                    chunk_ids_to_delete.append(doc_id)
            
            if chunk_ids_to_delete:
                collection.delete(ids=chunk_ids_to_delete)
                logger.info(f"Deleted {len(chunk_ids_to_delete)} old chunks")
        except Exception as e:
            logger.warning(f"Error deleting old chunks: {str(e)}, continuing with update")
        
        # Delete old document
        collection.delete(ids=[document_id])
        
        # Create new task for processing
        task_id = str(uuid.uuid4())
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document update queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Queue background processing with all chunking parameters
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            updated_content,
            updated_metadata,
            chunk_size,
            chunk_overlap,
            chunking_strategy,
            chunk_separator,
            max_chunks
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "message": "Document update queued for processing",
            "status": ProcessingStatus.PENDING
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(collection_name: str, document_id: str):
    """Delete a document and its chunks"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Try to delete document chunks if they exist
        try:
            # Get all documents in collection to find chunks manually
            all_results = collection.get(include=["metadatas"])
            chunk_ids_to_delete = []
            
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                # Check if this is a chunk of our document
                if metadata.get("parent_id") == document_id and metadata.get("is_chunk") is True:
                    chunk_ids_to_delete.append(doc_id)
            
            if chunk_ids_to_delete:
                collection.delete(ids=chunk_ids_to_delete)
                logger.info(f"Deleted {len(chunk_ids_to_delete)} chunks for document {document_id}")
        except Exception as chunk_error:
            logger.warning(f"Error deleting chunks: {str(chunk_error)}, continuing with document deletion")
        
        # Delete main document
        try:
            collection.delete(ids=[document_id])
            logger.info(f"Deleted document {document_id}")
        except Exception as doc_error:
            logger.error(f"Error deleting main document: {str(doc_error)}")
            raise HTTPException(status_code=404, detail=f"Document not found or already deleted: {str(doc_error)}")
        
        return {"message": f"Document '{document_id}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Document version endpoints

@app.get("/collections/{collection_name}/documents/by-name/{document_name}/versions")
async def list_document_versions(collection_name: str, document_name: str):
    """Get all versions of a document by name"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        all_results = collection.get(include=["documents", "metadatas"])
        
        versions = []
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Only include documents with matching name (not chunks)
            if metadata.get("name") == document_name and metadata.get("is_chunk") is False:
                versions.append({
                    "id": doc_id,
                    "version": metadata.get("version", 1),
                    "is_latest": metadata.get("is_latest", False),
                    "created_at": metadata.get("created_at", ""),
                    "updated_at": metadata.get("updated_at", ""),
                    "purpose": metadata.get("purpose", ""),
                    "tags": metadata.get("tags", ""),
                    "chunk_count": metadata.get("chunk_count", 1)
                })
        
        # Sort by version descending
        versions.sort(key=lambda x: x["version"], reverse=True)
        
        return {
            "document_name": document_name,
            "versions": versions,
            "total_versions": len(versions)
        }
    except Exception as e:
        logger.error(f"Error listing document versions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Processing status endpoints

@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get processing status of a task"""
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return processing_status[task_id]


@app.get("/tasks")
async def list_tasks(status: Optional[ProcessingStatus] = None):
    """List all tasks, optionally filtered by status"""
    tasks = list(processing_status.values())
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    return {"tasks": tasks, "total": len(tasks)}


# Search endpoint

@app.post("/collections/{collection_name}/search")
async def search_documents(
    collection_name: str,
    query: str,
    n_results: int = 5
):
    """Search for similar documents in a collection"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                search_results.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0
                })
        
        return {
            "query": query,
            "results": search_results,
            "count": len(search_results)
        }
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Analytics endpoints

@app.get("/analytics/stats")
async def get_stats():
    """Get overall system statistics"""
    try:
        collections = chroma_client.list_collections()
        
        total_collections = len(collections)
        total_documents = 0
        total_chunks = 0
        collection_details = []
        
        for collection in collections:
            col = chroma_client.get_collection(
                name=collection.name,
                embedding_function=embedding_function
            )
            all_items = col.get(include=["metadatas"])
            
            # Count actual documents (not chunks)
            documents = [item for item in all_items['metadatas'] if not item.get('is_chunk', False)]
            chunks = [item for item in all_items['metadatas'] if item.get('is_chunk', False)]
            
            doc_count = len(documents)
            chunk_count = len(chunks)
            
            total_documents += doc_count
            total_chunks += chunk_count
            
            collection_details.append({
                "name": collection.name,
                "document_count": doc_count,
                "chunk_count": chunk_count,
                "metadata": collection.metadata or {}
            })
        
        return {
            "total_collections": total_collections,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "collections": collection_details
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/recent-activity")
async def get_recent_activity(limit: int = 10):
    """Get recent activity (from task history)"""
    try:
        # Get recent completed tasks
        recent_tasks = sorted(
            processing_status.values(),
            key=lambda x: x.get("updated_at", x.get("created_at", "")),
            reverse=True
        )[:limit]
        
        activities = []
        for task in recent_tasks:
            activity_type = "unknown"
            if "create" in task.get("message", "").lower() or "upload" in task.get("message", "").lower():
                activity_type = "upload"
            elif "update" in task.get("message", "").lower():
                activity_type = "update"
            elif "delete" in task.get("message", "").lower():
                activity_type = "delete"
            
            activities.append({
                "type": activity_type,
                "message": task.get("message", ""),
                "status": task.get("status", ""),
                "timestamp": task.get("updated_at", task.get("created_at", "")),
                "collection": task.get("collection_name", "")
            })
        
        return {"activities": activities}
    except Exception as e:
        logger.error(f"Error getting recent activity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag management endpoints

@app.get("/tags")
async def get_all_tags():
    """Get all unique tags across all collections"""
    try:
        collections = chroma_client.list_collections()
        tag_counts = {}
        
        for collection in collections:
            col = chroma_client.get_collection(
                name=collection.name,
                embedding_function=embedding_function
            )
            all_items = col.get(include=["metadatas"])
            
            for metadata in all_items['metadatas']:
                if metadata.get('is_chunk', False):
                    continue
                    
                tags_str = metadata.get('tags', '')
                if tags_str:
                    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                    for tag in tags:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        # Sort by count (most popular first)
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
            "total": len(sorted_tags)
        }
    except Exception as e:
        logger.error(f"Error getting tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/tags")
async def get_collection_tags(collection_name: str):
    """Get all unique tags in a specific collection"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        all_items = collection.get(include=["metadatas"])
        
        tag_counts = {}
        for metadata in all_items['metadatas']:
            if metadata.get('is_chunk', False):
                continue
                
            tags_str = metadata.get('tags', '')
            if tags_str:
                tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "collection": collection_name,
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
            "total": len(sorted_tags)
        }
    except Exception as e:
        logger.error(f"Error getting collection tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Bulk operations endpoints

class BulkDeleteRequest(BaseModel):
    document_ids: List[str]


@app.post("/collections/{collection_name}/documents/bulk-delete")
async def bulk_delete_documents(
    collection_name: str,
    request: BulkDeleteRequest
):
    """Delete multiple documents at once"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        deleted_count = 0
        errors = []
        
        for doc_id in request.document_ids:
            try:
                # Get all items to find chunks
                all_items = collection.get(include=["metadatas"])
                
                # Find chunks for this document
                chunk_ids = []
                for i, metadata in enumerate(all_items['metadatas']):
                    if metadata.get('parent_id') == doc_id and metadata.get('is_chunk', False):
                        chunk_ids.append(all_items['ids'][i])
                
                # Delete chunks
                if chunk_ids:
                    collection.delete(ids=chunk_ids)
                
                # Delete main document
                collection.delete(ids=[doc_id])
                deleted_count += 1
                
            except Exception as e:
                errors.append({"document_id": doc_id, "error": str(e)})
        
        return {
            "deleted": deleted_count,
            "total": len(request.document_ids),
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkUpdateTagsRequest(BaseModel):
    document_ids: List[str]
    tags: str
    mode: str = "replace"  # "replace", "append", or "remove"


@app.post("/collections/{collection_name}/documents/bulk-update-tags")
async def bulk_update_tags(
    collection_name: str,
    request: BulkUpdateTagsRequest
):
    """Update tags for multiple documents"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        updated_count = 0
        errors = []
        
        for doc_id in request.document_ids:
            try:
                # Get current document
                result = collection.get(ids=[doc_id], include=["metadatas"])
                if not result['ids']:
                    errors.append({"document_id": doc_id, "error": "Document not found"})
                    continue
                
                current_metadata = result['metadatas'][0]
                current_tags = current_metadata.get('tags', '')
                
                # Update tags based on mode
                if request.mode == "replace":
                    new_tags = request.tags
                elif request.mode == "append":
                    existing = set([t.strip() for t in current_tags.split(',') if t.strip()])
                    new = set([t.strip() for t in request.tags.split(',') if t.strip()])
                    new_tags = ', '.join(sorted(existing.union(new)))
                elif request.mode == "remove":
                    existing = set([t.strip() for t in current_tags.split(',') if t.strip()])
                    to_remove = set([t.strip() for t in request.tags.split(',') if t.strip()])
                    new_tags = ', '.join(sorted(existing - to_remove))
                else:
                    new_tags = request.tags
                
                # Update metadata
                current_metadata['tags'] = new_tags
                collection.update(
                    ids=[doc_id],
                    metadatas=[current_metadata]
                )
                
                updated_count += 1
                
            except Exception as e:
                errors.append({"document_id": doc_id, "error": str(e)})
        
        return {
            "updated": updated_count,
            "total": len(request.document_ids),
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error in bulk update tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
