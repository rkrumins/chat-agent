from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form, Depends
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
import os
import sys

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Microservices components are loaded lazily to avoid blocking the event loop
# The config module creates SQLAlchemy connections that conflict with uvicorn's async handling
_microservices_loaded = False
_get_db = None
_ingestion_client = None
_file_storage = None


def get_microservices():
    """
    Lazy loader for microservices components.
    Returns (get_db, ingestion_client, file_storage, enabled).
    Only imports on first call to avoid blocking during startup.
    """
    global _microservices_loaded, _get_db, _ingestion_client, _file_storage
    
    if not _microservices_loaded:
        try:
            from config import get_db as db_getter, IngestionJob, JobStatus as DBJobStatus, init_db, ensure_directories
            from ingestion_client import IngestionClient, FileStorageManager
            
            # Initialize database and directories now (at first use, not import time)
            init_db()
            ensure_directories()
            
            _get_db = db_getter
            _ingestion_client = IngestionClient()
            _file_storage = FileStorageManager()
            _microservices_loaded = True
            logger.info("Microservices components loaded successfully")
        except ImportError as e:
            logger.warning(f"Microservices not available: {e}")
            _microservices_loaded = True  # Mark as loaded to avoid retry
    
    return _get_db, _ingestion_client, _file_storage, (_get_db is not None)


# For backwards compatibility, these will be None until first use
MICROSERVICES_ENABLED = None  # Will be determined on first use
get_db = None  # Use get_microservices() instead


from utils import (
    validate_file_size, validate_content, validate_chunking_parameters,
    validate_chunk_quality, calculate_content_hash, detect_duplicate_content,
    sanitize_filename, estimate_processing_time, MAX_FILE_SIZE
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

# Initialize embedding function
# Supports both sentence-transformers and Gemini embeddings
# Configure via environment variables:
#   EMBEDDING_PROVIDER: "sentence-transformers" (default) or "gemini"
#   EMBEDDING_MODEL: Model name (e.g., "all-mpnet-base-v2" or "models/embedding-001")
#   GOOGLE_APPLICATION_CREDENTIALS: Path to GCP service account JSON key (for Gemini)
#   GOOGLE_API_KEY: Google API key (alternative to service account)
from embedding_utils import get_embedding_function

embedding_provider = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
embedding_model = os.getenv("EMBEDDING_MODEL", None)
service_account_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", None)

embedding_function = get_embedding_function(
    provider=embedding_provider,
    model_name=embedding_model,
    service_account_path=service_account_path
)

# Get embedding dimension for metadata
def get_embedding_dimension():
    """Get the dimension of the current embedding model"""
    try:
        test_embedding = embedding_function(["test"])
        return len(test_embedding[0]) if test_embedding else 768
    except:
        # Default dimensions based on common models
        if embedding_provider == "gemini":
            return 768  # Gemini models are 768 dimensions
        elif embedding_model and "mini" in embedding_model.lower():
            return 384  # MiniLM models are 384 dimensions
        else:
            return 768  # Default to 768 for most models

embedding_dimension = get_embedding_dimension()

logger.info(f"Embedding provider: {embedding_provider}, model: {embedding_model or 'default'}, dimension: {embedding_dimension}")

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
    tags: Optional[str] = ""  # Changed to string (comma-separated)
    document_type: Optional[str] = None  # Optional: 'book', 'definition', 'article', 'blog_post', 'poem', 'unknown'
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


class CallbackPayload(BaseModel):
    """Payload received from ingestion service for status updates."""
    job_id: str
    status: str
    progress: int
    message: Optional[str] = None
    error: Optional[str] = None
    document_id: Optional[str] = None
    collection_name: Optional[str] = None
    document_type: Optional[str] = None
    chunks_created: Optional[int] = None
    timestamp: Optional[datetime] = None


# File parsing functions (kept for legacy fallback mode)

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
    """
    lines = text.split('\n')
    chunks = [line.strip() for line in lines if line.strip()]
    
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
        overlap: Overlap size in characters or elements (default 200)
        strategy: Chunking strategy - "semantic", "size", "lines", "paragraphs", "sentences", "custom"
        separator: Custom separator for "custom" strategy (or override for paragraphs)
        max_chunks: Optional limit on total number of chunks
    
    Returns:
        List of text chunks based on the specified strategy
    """
    if not text or not text.strip():
        return []
    
    # Normalize strategy name
    strategy = strategy.lower() if strategy else "semantic"
    
    # Route to appropriate chunking strategy
    if strategy == "lines":
        return chunk_by_lines(text, max_chunks)
    
    elif strategy == "paragraphs":
        sep = separator if separator else '\n\n'
        return chunk_by_paragraphs(text, separator=sep, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    
    elif strategy == "sentences":
        return chunk_by_sentences(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    
    elif strategy == "size":
        return chunk_by_size(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    
    elif strategy == "custom":
        if not separator:
            # Fallback to paragraphs if no separator provided
            separator = '\n\n'
        return chunk_by_custom_separator(text, separator=separator, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    
    else:
        # Default: semantic chunking (smart chunking with Mix-of-Granularity)
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
    content: Optional[str],
    metadata: Dict[str, Any],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    chunking_strategy: str = "semantic",
    chunk_separator: Optional[str] = None,
    max_chunks: Optional[int] = None,
    version: int = 1,
    max_retries: int = 3,
    file_content: Optional[bytes] = None,
    filename: Optional[str] = None
):
    """Process document asynchronously with status updates, validation, and error recovery"""
    retry_count = 0
    last_error = None
    
    while retry_count <= max_retries:
        try:
            # Update status
            processing_status[task_id]["status"] = ProcessingStatus.PROCESSING
            processing_status[task_id]["message"] = "Parsing file..." if file_content else ("Validating document content..." if retry_count == 0 else f"Retrying (attempt {retry_count + 1}/{max_retries + 1})...")
            processing_status[task_id]["progress"] = 5
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Step 1: Parse file if file_content is provided (for file uploads)
            if file_content is not None and filename:
                try:
                    content = parse_file(filename, file_content)
                    processing_status[task_id]["message"] = "File parsed successfully, validating content..."
                    processing_status[task_id]["progress"] = 8
                    processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
                except Exception as e:
                    raise ValueError(f"Error parsing file: {str(e)}")
            
            if content is None:
                raise ValueError("No content provided - either content or file_content must be provided")
            
            # Step 2: Validate content
            is_valid, error_msg, sanitized_content = validate_content(content)
            if not is_valid:
                raise ValueError(f"Content validation failed: {error_msg}")
            
            content = sanitized_content  # Use sanitized content
            
            # Step 3: Validate chunking parameters
            is_valid, error_msg = validate_chunking_parameters(
                chunk_size, chunk_overlap, chunking_strategy, max_chunks
            )
            if not is_valid:
                raise ValueError(f"Chunking parameter validation failed: {error_msg}")
            
            # Step 4: Check for duplicates (optional - can be disabled in metadata)
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
            
            # Step 6: Chunk document
            processing_status[task_id]["message"] = "Chunking document..."
            processing_status[task_id]["progress"] = 20
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Use chunking strategy from metadata or parameters
            strategy = metadata.get("chunking_strategy") or chunking_strategy or "semantic"
            separator = metadata.get("chunk_separator") or chunk_separator
            max_chunks_param = metadata.get("max_chunks") or max_chunks
            
            chunks = chunk_text(
                content, 
                chunk_size=chunk_size, 
                overlap=chunk_overlap,
                strategy=strategy,
                separator=separator,
                max_chunks=max_chunks_param
            )
            
            # Step 7: Validate chunk quality
            processing_status[task_id]["message"] = "Validating chunk quality..."
            processing_status[task_id]["progress"] = 40
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # For "lines" strategy, don't filter small chunks (each line is a valid chunk regardless of size)
            # For other strategies, use strict size validation
            strict_min_size = strategy != "lines"
            valid_chunks, quality_metrics = validate_chunk_quality(chunks, strict_min_size=strict_min_size)
            
            # Store quality metrics in processing status
            processing_status[task_id]["quality_metrics"] = quality_metrics
            
            # Check if we have any valid chunks
            if len(valid_chunks) == 0:
                raise ValueError("No valid chunks generated after quality validation. " + 
                               "; ".join(quality_metrics.get("issues", ["Unknown error"])))
            
            # Warn if many chunks were filtered
            if quality_metrics["filtered_chunks"] > 0:
                logger.warning(f"Filtered {quality_metrics['filtered_chunks']} invalid chunks. "
                             f"Valid chunks: {quality_metrics['valid_chunks']}/{quality_metrics['total_chunks']}")
            
            chunks = valid_chunks  # Use validated chunks
            
            processing_status[task_id]["message"] = f"Processing {len(chunks)} validated chunks..."
            processing_status[task_id]["progress"] = 50
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Step 7: Get or create collection
            processing_status[task_id]["message"] = "Preparing vector database collection..."
            processing_status[task_id]["progress"] = 55
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Get or create collection with embedding metadata
            try:
                collection = chroma_client.get_collection(name=collection_name)
            except:
                # Collection doesn't exist, create it with embedding metadata
                collection = chroma_client.create_collection(
                    name=collection_name,
                    metadata={
                        "description": metadata.get("description", ""),
                        "embedding_provider": embedding_provider,
                        "embedding_model": embedding_model or (f"sentence-transformers/all-mpnet-base-v2" if embedding_provider == "sentence-transformers" else "models/embedding-001"),
                        "embedding_dimension": embedding_dimension,
                    },
                    embedding_function=embedding_function
                )
            
            # Step 9: Detect document type
            processing_status[task_id]["message"] = "Detecting document type and creating contextual chunks..."
            processing_status[task_id]["progress"] = 60
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Detect document type (use provided type if available, otherwise auto-detect)
            document_type = metadata.get("document_type")
            if not document_type:
                document_type = detect_document_type(content, metadata)
                logger.info(f"Auto-detected document type: {document_type} for document: {metadata.get('name', 'Unknown')}")
            else:
                logger.info(f"Using provided document type: {document_type} for document: {metadata.get('name', 'Unknown')}")
            
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
        
            # Step 10: Prepare metadata for ChromaDB
            processing_status[task_id]["message"] = "Preparing metadata..."
            processing_status[task_id]["progress"] = 70
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            chroma_metadata = prepare_metadata_for_chroma(metadata)
            chroma_metadata["chunk_size"] = chunk_size
            chroma_metadata["chunk_overlap"] = chunk_overlap
            chroma_metadata["chunking_strategy"] = strategy  # Store chunking strategy used
            if separator:
                chroma_metadata["chunk_separator"] = separator
            if max_chunks_param:
                chroma_metadata["max_chunks"] = max_chunks_param
            chroma_metadata["version"] = version
            chroma_metadata["is_latest"] = True
            chroma_metadata["document_type"] = document_type  # CRITICAL: Add document type to metadata
            chroma_metadata["quality_metrics"] = json.dumps(quality_metrics)  # Store quality metrics
            # Add embedding model information to document metadata
            chroma_metadata["embedding_provider"] = embedding_provider
            chroma_metadata["embedding_model"] = embedding_model or (f"sentence-transformers/all-mpnet-base-v2" if embedding_provider == "sentence-transformers" else "models/embedding-001")
            chroma_metadata["embedding_dimension"] = embedding_dimension
            
            # Step 10: Store chunks in vector database
            processing_status[task_id]["message"] = "Storing in vector database with contextual chunks..."
            processing_status[task_id]["progress"] = 80
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
            # Store chunks with enhanced metadata and contextual prefixes
            # Always store chunks, even if there's only one, for consistency
            if len(chunks) >= 1:
                chunk_ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
                contextual_chunks = []
                chunk_metadata = []
                
                document_name = metadata.get("name", "Unknown")
                
                for i, chunk in enumerate(chunks):
                    # Store chunks directly without contextual prefix
                    # Document metadata is already in chunk_metadata and will be used for filtering/formatting
                    # This preserves more actual content space per chunk
                    contextual_chunks.append(chunk)
                    
                    chunk_meta = {
                        **chroma_metadata,
                        "chunk_index": i,
                        "chunk_number": i + 1,  # Human-readable chunk number (1-indexed)
                        "total_chunks": len(chunks),
                        "parent_id": document_id,
                        "parent_name": document_name,
                        "is_chunk": True,
                        # Ensure document name is preserved for reference
                        "document_name": document_name,
                        "document_version": version,
                        "document_type": document_type,  # CRITICAL: Document type in chunk metadata
                    }
                    chunk_metadata.append(chunk_meta)
                
                # Add chunks to collection with metadata
                # Document type and name are stored in metadata, not in chunk text
                # This preserves more actual content space per chunk
                collection.add(
                    documents=contextual_chunks,  # Raw chunks without prefixes
                    metadatas=chunk_metadata,
                    ids=chunk_ids
                )
                
                logger.info(f"Stored {len(contextual_chunks)} chunks for document type: {document_type}")
            
            # Step 11: Store full document
            processing_status[task_id]["message"] = "Storing document metadata..."
            processing_status[task_id]["progress"] = 90
            processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
            
            # Calculate content statistics
            content_length = len(content)
            word_count = len(content.split()) if content else 0
            
            full_doc_metadata = {
                **chroma_metadata,
                "is_chunk": False,
                "chunk_count": len(chunks),
                "document_type": document_type,  # Ensure document type is stored
                "content_length": content_length,  # Add character count
                "word_count": word_count,  # Add word count
                "updated_at": datetime.utcnow().isoformat()
            }
            
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
            
            # Get collection metadata, and add default embedding info if missing
            collection_metadata = col.metadata or {}
            
            # If embedding metadata is missing, try to infer it from existing embeddings
            if not collection_metadata.get("embedding_model"):
                try:
                    # Try to get a sample embedding to determine dimension
                    sample = col.get(limit=1, include=["embeddings"])
                    if sample["ids"] and sample["embeddings"]:
                        embedding_dim = len(sample["embeddings"][0])
                        # Infer model based on dimension
                        if embedding_dim == 384:
                            collection_metadata["embedding_model"] = "sentence-transformers/all-MiniLM-L6-v2"
                            collection_metadata["embedding_provider"] = "sentence-transformers"
                            collection_metadata["embedding_dimension"] = 384
                        elif embedding_dim == 768:
                            # Could be either mpnet or gemini - default to mpnet
                            collection_metadata["embedding_model"] = "sentence-transformers/all-mpnet-base-v2"
                            collection_metadata["embedding_provider"] = "sentence-transformers"
                            collection_metadata["embedding_dimension"] = 768
                except:
                    # If we can't infer, use current default
                    collection_metadata["embedding_model"] = embedding_model or (f"sentence-transformers/all-mpnet-base-v2" if embedding_provider == "sentence-transformers" else "models/embedding-001")
                    collection_metadata["embedding_provider"] = embedding_provider
                    collection_metadata["embedding_dimension"] = embedding_dimension
            
            result_collections.append({
                "name": col.name,
                "id": col.id,
                "metadata": collection_metadata,
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
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model or (f"sentence-transformers/all-mpnet-base-v2" if embedding_provider == "sentence-transformers" else "models/embedding-001"),
                "embedding_dimension": embedding_dimension,
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
        error_msg = str(e)
        logger.error(f"Error creating collection: {error_msg}")
        
        # Provide user-friendly error message for validation errors
        if "Validation error" in error_msg or "Expected a name" in error_msg:
            user_friendly_msg = (
                "Invalid collection name. Collection names must:\n"
                "• Be 3-512 characters long\n"
                "• Contain only letters, numbers, dots (.), underscores (_), and hyphens (-)\n"
                "• Start and end with a letter or number\n"
                "• Not contain spaces\n\n"
                f"Example: Use 'software-engineering' or 'software_engineering' instead of '{collection.name}'"
            )
            raise HTTPException(status_code=400, detail=user_friendly_msg)
        
        raise HTTPException(status_code=400, detail=error_msg)


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
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Skip chunks
            if metadata.get("is_chunk") is True:
                continue
            
            # Skip old versions unless requested
            if not show_all_versions and metadata.get("is_latest") is False:
                continue
            
            content = all_results["documents"][i] if all_results["documents"] else ""
            
            # Calculate content_length and word_count if not in metadata
            if "content_length" not in metadata:
                metadata["content_length"] = len(content)
            if "word_count" not in metadata:
                metadata["word_count"] = len(content.split()) if content else 0
            
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
        
        # Calculate content_length and word_count if not in metadata
        if "content_length" not in metadata:
            metadata["content_length"] = len(content)
        if "word_count" not in metadata:
            metadata["word_count"] = len(content.split()) if content else 0
        
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
        
        # Prepare metadata
        metadata = {
            "name": document.metadata.name,
            "purpose": document.metadata.purpose or "",
            "tags": document.metadata.tags or "",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **document.metadata.custom_metadata
        }
        
        # Queue background processing
        background_tasks.add_task(
            process_document_async,
            task_id=task_id,
            collection_name=collection_name,
            document_id=document_id,
            content=document.content,
            metadata=metadata,
            chunk_size=document.chunk_size,
            chunk_overlap=document.chunk_overlap,
            chunking_strategy=document.chunking_strategy or "semantic",
            chunk_separator=document.chunk_separator,
            max_chunks=document.max_chunks,
            version=version
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
    collection_name: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    purpose: str = Form(""),
    tags: str = Form(""),
    document_type: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    chunking_strategy: str = Form("semantic"),
    chunk_separator: str = Form(None),
    max_chunks: int = Form(None),
    custom_metadata: str = Form("{}"),
    create_new_version: bool = Form(False),
    background_tasks: BackgroundTasks = None
):
    """Upload and process a document file via ingestion microservice"""
    try:
        # Step 1: Validate file size (quick check)
        file_content = await file.read()
        file_size = len(file_content)
        
        is_valid, error_msg = validate_file_size(file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Step 2: Sanitize filename and validate extension (quick check)
        sanitized_filename = sanitize_filename(file.filename)
        extension = Path(sanitized_filename).suffix.lower()
        supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.text', '.json']
        if extension not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {extension}. Supported: {', '.join(supported_extensions)}"
            )
        
        # Step 3: Validate chunking parameters (quick check)
        is_valid, error_msg = validate_chunking_parameters(
            chunk_size, chunk_overlap, chunking_strategy, max_chunks
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Get or create collection
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
        
        # Parse custom metadata
        try:
            custom_meta = json.loads(custom_metadata) if custom_metadata else {}
        except json.JSONDecodeError:
            custom_meta = {}
        
        # Prepare metadata
        metadata = {
            "name": name,
            "purpose": purpose,
            "tags": tags,
            "filename": sanitized_filename,
            "original_filename": file.filename,
            "file_type": extension,
            "file_size": file_size,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **custom_meta
        }
        
        # Convert max_chunks to int if provided
        max_chunks_int = None
        if max_chunks is not None:
            try:
                max_chunks_int = int(max_chunks) if max_chunks != "null" and max_chunks != "" else None
            except (ValueError, TypeError):
                max_chunks_int = None
        
        # Check if microservices are enabled (lazy load on first use)
        db_getter, ingestion_client, file_storage, microservices_enabled = get_microservices()
        
        if microservices_enabled:
            # Use the new microservices architecture
            db = next(db_getter())
            
            try:
                # Store file using content-addressed storage
                stored_file, collection_link, is_new = file_storage.store_file(
                    file_content=file_content,
                    original_filename=sanitized_filename,
                    collection_name=collection_name,
                    document_id=document_id,
                    db=db
                )
                
                # Get the absolute file path for ingestion
                file_path = str(file_storage.get_file_path(stored_file))
                
                # Initialize processing status (for backwards compatibility with frontend)
                processing_status[task_id] = {
                    "task_id": task_id,
                    "document_id": document_id,
                    "status": ProcessingStatus.PENDING,
                    "message": "Document queued for ingestion",
                    "progress": 0,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                # Trigger ingestion via REST API
                try:
                    result = await ingestion_client.trigger_ingestion(
                        job_id=task_id,
                        file_id=stored_file.id,
                        file_path=file_path,
                        collection_name=collection_name,
                        document_id=document_id,
                        metadata=metadata,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                        chunking_strategy=chunking_strategy or "semantic",
                        chunk_separator=chunk_separator if chunk_separator and chunk_separator != "null" else None,
                        max_chunks=max_chunks_int,
                        document_type=document_type,
                        version=version,
                        create_new_version=create_new_version
                    )
                    logger.info(f"Ingestion triggered for document {document_id}: {result}")
                except Exception as e:
                    logger.error(f"Failed to trigger ingestion: {e}")
                    # Update status to failed
                    processing_status[task_id]["status"] = ProcessingStatus.FAILED
                    processing_status[task_id]["message"] = f"Failed to trigger ingestion: {str(e)}"
                    raise HTTPException(status_code=500, detail=f"Failed to trigger ingestion service: {str(e)}")
                
            finally:
                db.close()

        else:
            # Fall back to legacy BackgroundTasks approach
            logger.warning("Microservices not enabled, using legacy BackgroundTasks")
            
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
            
            # Store chunking parameters in metadata
            metadata["chunking_strategy"] = chunking_strategy or "semantic"
            if chunk_separator:
                metadata["chunk_separator"] = chunk_separator
            if max_chunks_int:
                metadata["max_chunks"] = max_chunks_int
            
            # Queue background processing
            if background_tasks:
                background_tasks.add_task(
                    process_document_async,
                    task_id=task_id,
                    collection_name=collection_name,
                    document_id=document_id,
                    content=None,
                    metadata=metadata,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    chunking_strategy=chunking_strategy or "semantic",
                    chunk_separator=chunk_separator if chunk_separator and chunk_separator != "null" else None,
                    max_chunks=max_chunks_int,
                    version=version,
                    file_content=file_content,
                    filename=sanitized_filename
                )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": version,
            "message": f"Document queued for processing (version {version})",
            "status": ProcessingStatus.PENDING,
            "filename": file.filename,
            "microservices_enabled": microservices_enabled
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
            # Update document_type if provided
            if update.metadata.document_type is not None:
                updated_metadata["document_type"] = update.metadata.document_type
        
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
            task_id=task_id,
            collection_name=collection_name,
            document_id=document_id,
            content=updated_content,
            metadata=updated_metadata,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunking_strategy=chunking_strategy,
            chunk_separator=chunk_separator,
            max_chunks=max_chunks
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


@app.get("/collections/{collection_name}/documents/{document_id}/chunks")
async def get_document_chunks(
    collection_name: str,
    document_id: str,
    skip: int = 0,
    limit: int = 100
):
    """Get all chunks for a specific document with metadata"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get all items from collection
        # Note: ids are always returned, don't include them in the include parameter
        all_results = collection.get(include=["documents", "metadatas"])
        
        if not all_results["ids"]:
            logger.warning(f"No items found in collection '{collection_name}'")
            return {
                "chunks": [],
                "total": 0,
                "skip": skip,
                "limit": limit,
                "document_id": document_id
            }
        
        # Filter chunks that belong to this document
        chunks = []
        for i, chunk_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Check if this is a chunk belonging to the document
            is_chunk = metadata.get("is_chunk")
            if is_chunk is True:
                # Check if it belongs to this document by parent_id
                parent_id = metadata.get("parent_id")
                
                # Also check if chunk_id pattern matches (format: {document_id}_chunk_{index})
                belongs_to_document = (
                    parent_id == document_id or 
                    chunk_id.startswith(f"{document_id}_chunk_") or
                    chunk_id.startswith(f"{document_id}_chunk")
                )
                
                if belongs_to_document:
                    content = all_results["documents"][i] if all_results["documents"] else ""
                    
                    # Calculate chunk statistics
                    chunk_length = len(content)
                    chunk_word_count = len(content.split()) if content else 0
                    
                    chunks.append({
                        "id": chunk_id,
                        "content": content,
                        "metadata": metadata,
                        "chunk_number": metadata.get("chunk_number", 0),
                        "total_chunks": metadata.get("total_chunks", 0),
                        "chunk_index": metadata.get("chunk_index", 0),
                        "document_type": metadata.get("document_type", "unknown"),
                        "parent_id": parent_id,
                        "parent_name": metadata.get("parent_name") or metadata.get("name", "Unknown"),
                        "length": chunk_length,  # Character count for UI
                        "word_count": chunk_word_count  # Word count for UI
                    })
        
        # Sort chunks by chunk_number
        chunks.sort(key=lambda x: x.get("chunk_number", 0))
        
        logger.info(f"Found {len(chunks)} chunks for document {document_id} in collection {collection_name}")
        
        # Apply pagination
        total_chunks = len(chunks)
        paginated_chunks = chunks[skip:skip+limit]
        
        return {
            "chunks": paginated_chunks,
            "total": total_chunks,
            "skip": skip,
            "limit": limit,
            "document_id": document_id
        }
    except Exception as e:
        logger.error(f"Error getting document chunks for {document_id} in {collection_name}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting document chunks: {str(e)}")


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


@app.post("/api/jobs/{job_id}/callback")
async def receive_job_callback(job_id: str, payload: CallbackPayload):
    """
    Receive status callback from ingestion service.
    Updates the in-memory processing_status dict for backwards compatibility.
    """
    logger.info(f"Received callback for job {job_id}: {payload.status} ({payload.progress}%)")
    
    # Map ingestion service status to our ProcessingStatus enum
    status_map = {
        "queued": ProcessingStatus.PENDING,
        "processing": ProcessingStatus.PROCESSING,
        "completed": ProcessingStatus.COMPLETED,
        "failed": ProcessingStatus.FAILED
    }
    
    mapped_status = status_map.get(payload.status.lower(), ProcessingStatus.PROCESSING)
    
    # Update in-memory status (for backwards compatibility with frontend)
    processing_status[job_id] = {
        "task_id": job_id,
        "document_id": payload.document_id or "",
        "status": mapped_status,
        "message": payload.message or "",
        "progress": payload.progress,
        "created_at": processing_status.get(job_id, {}).get("created_at", datetime.utcnow().isoformat()),
        "updated_at": payload.timestamp.isoformat() if payload.timestamp else datetime.utcnow().isoformat(),
        "chunk_count": payload.chunks_created,
        "document_type": payload.document_type,
        "error": payload.error
    }
    
    return {"status": "received", "job_id": job_id}




@app.post("/collections/{collection_name}/search")
async def search_documents(
    collection_name: str,
    query: str,
    n_results: int = 5
):
    """Search for similar documents in a collection"""
    try:
        # Try to get collection with current embedding function first
        try:
            collection = chroma_client.get_collection(
                name=collection_name,
                embedding_function=embedding_function
            )
            # Collection uses current embedding function - can query directly
            query_embedding_func = embedding_function
        except Exception as e:
            # If that fails, try to get collection without embedding function
            # This might be an old collection with different embedding dimensions
            try:
                collection = chroma_client.get_collection(name=collection_name)
                
                # Check the collection's embedding dimension
                # Get a sample to check dimension
                sample = collection.get(limit=1, include=["embeddings"])
                if sample["ids"] and sample["embeddings"]:
                    existing_dim = len(sample["embeddings"][0])
                    current_dim = len(embedding_function(["test"])[0]) if embedding_function else 768
                    
                    if existing_dim != current_dim:
                        logger.warning(
                            f"Collection '{collection_name}' has embedding dimension {existing_dim}, "
                            f"but current model uses {current_dim}. This collection may need to be migrated."
                        )
                        # For old collections, we can't query with the new embedding function
                        # Return empty results with a helpful message
                        return {
                            "query": query,
                            "results": [],
                            "count": 0,
                            "warning": f"Collection uses different embedding model (dimension {existing_dim}). "
                                     f"Please re-upload documents to this collection to use the new embedding model."
                        }
                
                # Collection exists but might have issues - try to query anyway
                query_embedding_func = None  # Use collection's default
            except Exception as e2:
                logger.error(f"Collection '{collection_name}' not found or inaccessible: {str(e2)}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Collection '{collection_name}' not found or inaccessible: {str(e2)}"
                )
        
        # Perform the search query
        try:
            if query_embedding_func:
                # Use the current embedding function
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
            else:
                # Collection doesn't match current embedding function
                # Try to query without specifying embedding function (uses collection's default)
                results = collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
        except Exception as query_error:
            error_msg = str(query_error)
            if "dimension" in error_msg.lower() or "embedding" in error_msg.lower():
                logger.error(
                    f"Embedding dimension mismatch for collection '{collection_name}': {error_msg}"
                )
                return {
                    "query": query,
                    "results": [],
                    "count": 0,
                    "warning": f"This collection uses a different embedding model. "
                             f"Please re-upload documents to migrate to the current model."
                }
            else:
                # Re-raise other query errors
                raise
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching documents in collection '{collection_name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error searching documents: {str(e)}")


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
