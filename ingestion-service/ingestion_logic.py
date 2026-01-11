"""
Core ingestion logic for document processing.
Handles file parsing, chunking, embedding, and ChromaDB storage.
Moved from backend/main.py to enable standalone ingestion microservice.
"""

import io
import re
import json
import asyncio
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Document parsing libraries
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

logger = logging.getLogger(__name__)

# ============================================================================
# File Parsing Functions
# ============================================================================

def parse_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    if PdfReader is None:
        raise ValueError("PDF parsing not available. Install PyPDF2.")
    
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise ValueError(f"Error parsing PDF: {str(e)}")


def parse_docx(file_content: bytes) -> str:
    """Extract text from Word document"""
    if DocxDocument is None:
        raise ValueError("DOCX parsing not available. Install python-docx.")
    
    try:
        docx_file = io.BytesIO(file_content)
        doc = DocxDocument(docx_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise ValueError(f"Error parsing DOCX: {str(e)}")


def parse_txt(file_content: bytes) -> str:
    """Extract text from TXT file"""
    try:
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return file_content.decode('latin-1')
        except Exception as e:
            raise ValueError(f"Error parsing TXT: {str(e)}")


def parse_json(file_content: bytes) -> str:
    """Extract text from JSON file"""
    try:
        data = json.loads(file_content.decode('utf-8'))
        return json.dumps(data, indent=2)
    except Exception as e:
        raise ValueError(f"Error parsing JSON: {str(e)}")


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
        raise ValueError(
            f"Unsupported file type: {extension}. Supported: PDF, DOCX, TXT, JSON"
        )
    
    return parser(file_content)


# ============================================================================
# Chunking Strategies
# ============================================================================

def chunk_by_lines(text: str, max_chunks: Optional[int] = None) -> List[str]:
    """Chunk text by lines (one line per chunk)."""
    lines = text.split('\n')
    chunks = [line.strip() for line in lines if line.strip()]
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


def chunk_by_paragraphs(
    text: str, 
    separator: str = '\n\n', 
    chunk_size: int = 2000, 
    overlap: int = 0, 
    max_chunks: Optional[int] = None
) -> List[str]:
    """Chunk text by paragraphs using a separator."""
    paragraphs = text.split(separator)
    processed_chunks = []
    
    for para in paragraphs:
        trimmed = para.strip()
        if not trimmed:
            continue
        
        if len(trimmed) > chunk_size:
            # Split paragraph into sentences
            sentence_pattern = r'([.!?]+)\s+'
            sentences = re.split(sentence_pattern, trimmed)
            
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
                        overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                        current_chunk = overlap_sentences + [sentence]
                        current_length = len(' '.join(current_chunk))
                        
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
            processed_chunks.append(trimmed)
            if max_chunks and len(processed_chunks) >= max_chunks:
                break
    
    if max_chunks:
        processed_chunks = processed_chunks[:max_chunks]
    
    return processed_chunks


def chunk_by_sentences(
    text: str, 
    chunk_size: int = 1000, 
    overlap: int = 200, 
    max_chunks: Optional[int] = None
) -> List[str]:
    """Chunk text by sentences, respecting chunk_size."""
    sentence_pattern = r'([.!?]+)\s+'
    sentences = re.split(sentence_pattern, text)
    
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
            
            if overlap > 0:
                overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                current_chunk = overlap_sentences + [sentence]
                current_length = len(' '.join(current_chunk))
                
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


def chunk_by_size(
    text: str, 
    chunk_size: int = 1000, 
    overlap: int = 200, 
    max_chunks: Optional[int] = None
) -> List[str]:
    """Chunk text by character size with word boundaries."""
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
            
            if overlap > 0:
                overlap_words = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                current_chunk = overlap_words + [word]
                current_length = len(' '.join(current_chunk))
                
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


def chunk_by_custom_separator(
    text: str, 
    separator: str, 
    chunk_size: int = 1000, 
    overlap: int = 0, 
    max_chunks: Optional[int] = None
) -> List[str]:
    """Chunk text using a custom separator."""
    chunks = text.split(separator)
    chunks = [chunk.strip() for chunk in chunks if chunk.strip()]
    
    if chunk_size:
        sized_chunks = []
        for chunk in chunks:
            if len(chunk) > chunk_size:
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
    
    if max_chunks:
        chunks = chunks[:max_chunks]
    
    return chunks


def chunk_text_semantic(
    text: str, 
    chunk_size: int = 1000, 
    overlap: int = 200, 
    max_chunks: Optional[int] = None
) -> List[str]:
    """
    Advanced semantic chunking with Mix-of-Granularity approach.
    Split text into overlapping chunks using sentence and paragraph 
    boundaries for better context preservation.
    """
    if not text or not text.strip():
        return []
    
    if len(text) <= chunk_size:
        result = [text.strip()]
        if max_chunks:
            result = result[:max_chunks]
        return result
    
    chunks = []
    
    sentence_pattern = r'([.!?]+)\s+'
    sentences = re.split(sentence_pattern, text)
    
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
    
    # Fallback: if sentence splitting fails, split by paragraphs
    if len(proper_sentences) == 0 or len(proper_sentences[0]) > chunk_size:
        paragraphs = text.split('\n\n')
        proper_sentences = []
        for para in paragraphs:
            if len(para.strip()) > chunk_size:
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
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_with_space = word + ' '
            word_length = len(word_with_space)
            
            if current_length + word_length > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                if overlap > 0:
                    overlap_words = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                    current_chunk = overlap_words + [word]
                    current_length = len(' '.join(current_chunk))
                    
                    if current_length > chunk_size:
                        current_chunk = [word]
                        current_length = word_length
                else:
                    current_chunk = [word]
                    current_length = word_length
            else:
                current_chunk.append(word)
                current_length += word_length
            
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
        if max_chunks and len(chunks) >= max_chunks:
            break
        
        sentence = sentence.strip()
        if not sentence:
            continue
            
        sentence_length = len(sentence)
        
        if sentence_length > chunk_size:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            
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
            if current_length + sentence_length + 1 > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                if max_chunks and len(chunks) >= max_chunks:
                    break
                
                if overlap > 0:
                    overlap_sentences = current_chunk[-max(1, len(current_chunk) * overlap // chunk_size):]
                    current_chunk = overlap_sentences + [sentence]
                    current_length = len(' '.join(current_chunk))
                    
                    if current_length > chunk_size:
                        current_chunk = [sentence]
                        current_length = sentence_length
                else:
                    current_chunk = [sentence]
                    current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length + 1
    
    if current_chunk and (not max_chunks or len(chunks) < max_chunks):
        chunks.append(' '.join(current_chunk))
    
    result = [chunk.strip() for chunk in chunks if chunk.strip()]
    if max_chunks:
        result = result[:max_chunks]
    return result


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
    Supports: semantic, size, lines, paragraphs, sentences, custom.
    """
    if not text or not text.strip():
        return []
    
    strategy = strategy.lower() if strategy else "semantic"
    
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
            separator = '\n\n'
        return chunk_by_custom_separator(text, separator=separator, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)
    else:
        return chunk_text_semantic(text, chunk_size=chunk_size, overlap=overlap, max_chunks=max_chunks)


# ============================================================================
# Document Processing Helpers
# ============================================================================

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
    content_lower = content[:2000].lower()
    lines = content.split('\n')
    avg_line_length = sum(len(line.strip()) for line in lines[:20]) / max(1, min(20, len(lines)))
    
    if avg_line_length < 50 and len(lines) > 5:
        if any(word in content_lower for word in ["verse", "stanza", "rhyme", "poem"]):
            return "poem"
    
    definition_patterns = [
        r'^[A-Z][a-z]+:\s*[A-Z]',
        r'^[A-Z][a-z]+\s+—\s+',
        r'^[A-Z][a-z]+\s+=\s+',
    ]
    definition_count = sum(1 for line in lines[:50] 
                          if any(re.match(pattern, line.strip()) for pattern in definition_patterns))
    if definition_count > 5:
        return "definition"
    
    if any(word in content_lower for word in ["abstract", "introduction", "conclusion", "references", "citation"]):
        return "article"
    
    if any(word in content_lower for word in ["posted on", "published", "tags:", "#", "read more"]):
        return "blog_post"
    
    if any(word in content_lower for word in ["chapter", "table of contents", "preface", "appendix"]):
        return "book"
    
    if len(content) > 5000:
        return "book"
    
    return "unknown"


def prepare_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare metadata for ChromaDB - convert lists to strings"""
    chroma_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, list):
            chroma_metadata[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            chroma_metadata[key] = json.dumps(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            chroma_metadata[key] = value
        else:
            chroma_metadata[key] = str(value)
    return chroma_metadata


def calculate_content_hash(content: str) -> str:
    """Calculate SHA-256 hash of content for duplicate detection."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def get_adaptive_chunk_params(
    document_type: str, 
    chunk_size: int, 
    chunk_overlap: int
) -> Tuple[int, int]:
    """Get adaptive chunk parameters based on document type."""
    if document_type == "definition":
        adaptive_chunk_size = min(800, max(500, chunk_size))
        adaptive_overlap = min(150, max(50, chunk_overlap))
    elif document_type == "book":
        adaptive_chunk_size = max(1000, min(2000, chunk_size))
        adaptive_overlap = max(200, min(400, chunk_overlap))
    elif document_type == "article":
        adaptive_chunk_size = max(800, min(1500, chunk_size))
        adaptive_overlap = max(150, min(300, chunk_overlap))
    else:
        adaptive_chunk_size = chunk_size
        adaptive_overlap = chunk_overlap
    
    return adaptive_chunk_size, adaptive_overlap
