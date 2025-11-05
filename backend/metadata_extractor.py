"""
Metadata extraction utilities for enhanced RAG performance
Following best practices for document and chunk metadata
"""
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def extract_content_type(text: str) -> str:
    """
    Infer the content type of a chunk.
    Returns: 'paragraph', 'list', 'code', 'table', 'heading', 'quote', 'mixed'
    """
    text = text.strip()
    
    # Check for code blocks
    if re.search(r'```[\s\S]*?```|`[^`]+`', text):
        return "code"
    
    # Check for tables (multiple lines with consistent separators)
    lines = text.split('\n')
    if len(lines) > 2:
        separator_count = sum(1 for line in lines if re.search(r'\|.*\|', line))
        if separator_count >= 2:
            return "table"
    
    # Check for lists
    list_patterns = [
        r'^\s*[-*+]\s+',  # Bullet points
        r'^\s*\d+[\.\)]\s+',  # Numbered lists
    ]
    list_lines = sum(1 for line in lines if any(re.match(pattern, line) for pattern in list_patterns))
    if list_lines > len(lines) * 0.3:  # More than 30% list items
        return "list"
    
    # Check for headings (short lines, all caps, or marked with #)
    if len(lines) == 1 and len(text) < 100:
        if text.isupper() or re.match(r'^#+\s+', text):
            return "heading"
    
    # Check for quotes
    if text.startswith('"') and text.endswith('"') or text.startswith("'") and text.endswith("'"):
        return "quote"
    
    # Default to paragraph
    if len(lines) == 1 or len(text.split('\n\n')) == 1:
        return "paragraph"
    
    return "mixed"


def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """
    Extract key topics/keywords from text chunk using simple heuristics.
    For production, consider using NLP libraries or LLM-based extraction.
    """
    # Remove common stop words and short words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had',
        'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
        'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
        'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how'
    }
    
    # Extract words (3+ characters, alphanumeric)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    
    # Filter stop words and count frequency
    word_freq = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
    
    # Get top keywords
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [word for word, freq in sorted_words[:max_keywords]]
    
    return keywords if keywords else ["general"]


def estimate_difficulty_level(text: str) -> str:
    """
    Heuristically estimate difficulty level of content.
    Returns: 'Beginner', 'Intermediate', 'Advanced'
    """
    text_lower = text.lower()
    
    # Advanced indicators
    advanced_keywords = [
        'algorithm', 'complexity', 'optimization', 'architecture', 'implementation',
        'sophisticated', 'advanced', 'expert', 'complex', 'intricate', 'nuanced',
        'abstract', 'theoretical', 'mathematical', 'quantum', 'neural network',
        'deep learning', 'machine learning', 'data structure', 'design pattern'
    ]
    
    # Beginner indicators
    beginner_keywords = [
        'introduction', 'overview', 'basic', 'simple', 'easy', 'getting started',
        'beginner', 'first', 'learn', 'tutorial', 'guide', 'step by step',
        'example', 'quick start', 'fundamentals', 'basics'
    ]
    
    advanced_count = sum(1 for keyword in advanced_keywords if keyword in text_lower)
    beginner_count = sum(1 for keyword in beginner_keywords if keyword in text_lower)
    
    if advanced_count > beginner_count and advanced_count >= 2:
        return "Advanced"
    elif beginner_count > advanced_count and beginner_count >= 2:
        return "Beginner"
    else:
        return "Intermediate"


def extract_section_title(text: str, previous_text: Optional[str] = None) -> Optional[str]:
    """
    Extract section title if available (from heading markers or first line).
    """
    # Check for markdown headings
    heading_match = re.match(r'^(#{1,6})\s+(.+)$', text.strip(), re.MULTILINE)
    if heading_match:
        return heading_match.group(2).strip()
    
    # Check first line if it looks like a title (short, capitalized)
    lines = text.strip().split('\n')
    if lines and len(lines[0]) < 100:
        first_line = lines[0].strip()
        # If it's all caps or title case and short, likely a title
        if (first_line.isupper() or first_line.istitle()) and len(first_line) < 80:
            return first_line
    
    return None


def extract_page_number(text: str, document_content: str, chunk_index: int) -> Optional[int]:
    """
    Attempt to extract page number if document has page markers.
    For PDFs, this should be set during parsing.
    """
    # Look for page markers in text
    page_match = re.search(r'\b(page|p\.?)\s*(\d+)\b', text, re.IGNORECASE)
    if page_match:
        try:
            return int(page_match.group(2))
        except ValueError:
            pass
    
    # If we have the full document, estimate based on position
    # This is a rough estimate
    if document_content:
        chunk_start_pos = 0  # Would need to track actual position
        estimated_page = max(1, int((chunk_index + 1) / 10))  # Rough estimate
        return estimated_page
    
    return None


def build_comprehensive_document_metadata(
    document_id: str,
    name: str,
    metadata: Dict[str, Any],
    collection_name: str,
    document_type: str,
    content: str,
    version: int = 1
) -> Dict[str, Any]:
    """
    Build comprehensive document-level metadata following RAG best practices.
    """
    # Parse tags if string
    tags = metadata.get("tags", "")
    if isinstance(tags, str):
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
    else:
        tag_list = tags if isinstance(tags, list) else []
    
    # Extract author from metadata, custom_metadata, or default
    author = (
        metadata.get("author") or 
        metadata.get("created_by") or 
        (metadata.get("custom_metadata", {}).get("author") if isinstance(metadata.get("custom_metadata"), dict) else None) or
        "unknown"
    )
    
    # Determine source (can be specified or inferred from collection)
    source = (
        metadata.get("source") or 
        (metadata.get("custom_metadata", {}).get("source") if isinstance(metadata.get("custom_metadata"), dict) else None) or
        collection_name or 
        "upload"
    )
    
    # Build comprehensive metadata
    doc_metadata = {
        # Core identifiers
        "doc_id": document_id,
        "document_id": document_id,  # Alias for compatibility
        "title": name,
        "document_name": name,  # Alias for compatibility
        
        # Temporal information
        "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
        "created_ts": metadata.get("created_at", datetime.utcnow().isoformat()),  # Timestamp alias
        "updated_at": metadata.get("updated_at", datetime.utcnow().isoformat()),
        "version": version,
        
        # Source and origin
        "source": source,
        "collection_name": collection_name,
        "document_type": document_type,
        
        # Content information
        "content_length": len(content),
        "word_count": len(content.split()),
        
        # Author and ownership
        "author": author,
        "creator": author,  # Alias
        
        # Categorization
        "tags": ", ".join(tag_list) if tag_list else "",
        "tag_list": tag_list,  # For filtering
        "purpose": metadata.get("purpose", ""),
        
        # File information (if available)
        "filename": metadata.get("filename", ""),
        "original_filename": metadata.get("original_filename", ""),
        "file_type": metadata.get("file_type", ""),
        "file_size": metadata.get("file_size", 0),
        
        # Versioning
        "is_latest": metadata.get("is_latest", True),
        "is_chunk": False,  # Document-level flag
        
        # Chunking parameters (for reference)
        "chunking_strategy": metadata.get("chunking_strategy", "semantic"),
        "chunk_count": metadata.get("chunk_count", 0),  # Include chunk_count if available
    }
    
    # Only include chunk_size and chunk_overlap if they're actually in the metadata
    # Don't apply defaults here - let the values come from the actual chunking parameters used
    if "chunk_size" in metadata and metadata["chunk_size"] is not None:
        doc_metadata["chunk_size"] = metadata["chunk_size"]
    if "chunk_overlap" in metadata and metadata["chunk_overlap"] is not None:
        doc_metadata["chunk_overlap"] = metadata["chunk_overlap"]
    
    # Add custom metadata
    if metadata.get("custom_metadata"):
        if isinstance(metadata["custom_metadata"], dict):
            doc_metadata.update(metadata["custom_metadata"])
    
    return doc_metadata


def build_comprehensive_chunk_metadata(
    chunk_id: str,
    chunk_index: int,
    chunk_text: str,
    document_metadata: Dict[str, Any],
    document_content: str,
    previous_chunk_text: Optional[str] = None,
    total_chunks: Optional[int] = None
) -> Dict[str, Any]:
    """
    Build comprehensive chunk-level metadata following RAG best practices.
    
    Args:
        total_chunks: Total number of chunks for this document (if not provided, will try to get from document_metadata)
    """
    # Extract chunk-specific metadata
    content_type = extract_content_type(chunk_text)
    topics = extract_keywords(chunk_text)
    difficulty = estimate_difficulty_level(chunk_text)
    section_title = extract_section_title(chunk_text, previous_chunk_text)
    
    # Get total chunks - prefer parameter, then document_metadata, then default to 1
    actual_total_chunks = total_chunks
    if actual_total_chunks is None:
        actual_total_chunks = document_metadata.get("chunk_count")
    if actual_total_chunks is None or actual_total_chunks == 0:
        actual_total_chunks = 1  # Fallback, but should be set
    
    # Build comprehensive chunk metadata
    chunk_metadata = {
        # Core identifiers
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
        "chunk_number": chunk_index + 1,  # Human-readable (1-indexed)
        
        # Parent document references (critical for RAG)
        "parent_id": document_metadata.get("doc_id") or document_metadata.get("document_id"),
        "parent_name": document_metadata.get("title") or document_metadata.get("document_name"),
        "document_id": document_metadata.get("doc_id") or document_metadata.get("document_id"),
        "document_name": document_metadata.get("title") or document_metadata.get("document_name"),
        "document_type": document_metadata.get("document_type", "unknown"),
        "document_version": document_metadata.get("version", 1),
        
        # Position and context
        "total_chunks": actual_total_chunks,
        "chunk_position": f"{chunk_index + 1} of {actual_total_chunks}",
        
        # Content characteristics
        "content_type": content_type,  # paragraph, list, code, table, etc.
        "topics": ", ".join(topics),  # Comma-separated for storage
        "topic_list": topics,  # List format for filtering
        "difficulty_level": difficulty,
        "section_title": section_title or "",
        
        # Content metrics
        "chunk_length": len(chunk_text),
        "word_count": len(chunk_text.split()),
        "char_count": len(chunk_text),
        
        # Source information (inherit from document)
        "source": document_metadata.get("source", ""),
        "collection_name": document_metadata.get("collection_name", ""),
        "author": document_metadata.get("author", ""),
        
        # Temporal (inherit from document)
        "created_at": document_metadata.get("created_at", ""),
        "created_ts": document_metadata.get("created_ts", ""),
        "updated_at": document_metadata.get("updated_at", ""),
        
        # Document tags (inherit for filtering)
        "document_tags": document_metadata.get("tags", ""),
        "document_purpose": document_metadata.get("purpose", ""),
        
        # Chunking information
        "chunking_strategy": document_metadata.get("chunking_strategy", "semantic"),
        
        # Flag
        "is_chunk": True,
    }
    
    # Add page number if available
    page_num = extract_page_number(chunk_text, document_content, chunk_index)
    if page_num:
        chunk_metadata["page_number"] = page_num
    
    return chunk_metadata

