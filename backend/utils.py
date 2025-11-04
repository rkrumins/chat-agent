"""
Utility functions for production-grade document processing
"""
import re
import hashlib
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Configuration constants
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MIN_CHUNK_SIZE = 10  # Minimum characters for a valid chunk
MAX_CHUNK_SIZE = 50000  # Maximum characters per chunk
MIN_CONTENT_LENGTH = 1  # Minimum document content length
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB content


def validate_file_size(file_size: int) -> Tuple[bool, Optional[str]]:
    """Validate file size is within acceptable limits"""
    if file_size <= 0:
        return False, "File is empty"
    if file_size > MAX_FILE_SIZE:
        return False, f"File size ({file_size / 1024 / 1024:.2f}MB) exceeds maximum allowed size ({MAX_FILE_SIZE / 1024 / 1024}MB)"
    return True, None


def validate_content(content: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and sanitize document content.
    Returns: (is_valid, error_message, sanitized_content)
    """
    if not content:
        return False, "Content is empty or missing", None
    
    # Check length
    content_length = len(content)
    if content_length < MIN_CONTENT_LENGTH:
        return False, f"Content too short (minimum {MIN_CONTENT_LENGTH} characters)", None
    if content_length > MAX_CONTENT_LENGTH:
        return False, f"Content too long ({content_length / 1024 / 1024:.2f}MB, maximum {MAX_CONTENT_LENGTH / 1024 / 1024}MB)", None
    
    # Normalize unicode (handle encoding issues)
    try:
        # Normalize to NFC form
        normalized = unicodedata.normalize('NFC', content)
        
        # Remove null bytes
        normalized = normalized.replace('\x00', '')
        
        # Remove control characters except newlines and tabs
        cleaned = ''.join(char for char in normalized 
                         if unicodedata.category(char)[0] != 'C' or char in ['\n', '\t', '\r'])
        
        # Check if content has meaningful text (not just whitespace/control chars)
        text_content = cleaned.strip()
        if len(text_content) < MIN_CONTENT_LENGTH:
            return False, "Content contains no meaningful text (only whitespace or control characters)", None
        
        return True, None, cleaned
    
    except Exception as e:
        logger.error(f"Error validating content: {str(e)}")
        return False, f"Content validation error: {str(e)}", None


def validate_chunking_parameters(chunk_size: int, chunk_overlap: int, 
                                 chunking_strategy: str, max_chunks: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate chunking parameters based on the selected strategy.
    Some strategies (like "lines") don't use chunk_size or overlap, so validation is more lenient.
    """
    strategy = chunking_strategy.lower() if chunking_strategy else "semantic"
    
    valid_strategies = ["semantic", "size", "lines", "paragraphs", "sentences", "custom"]
    if strategy not in valid_strategies:
        return False, f"Invalid chunking strategy '{chunking_strategy}'. Valid options: {', '.join(valid_strategies)}"
    
    # For "lines" strategy, chunk_size and overlap are not used, so validation is lenient
    if strategy == "lines":
        # Only check that chunk_size and overlap are non-negative (for logging/metadata purposes)
        if chunk_size < 0:
            return False, f"Chunk size ({chunk_size}) cannot be negative"
        if chunk_overlap < 0:
            return False, "Chunk overlap cannot be negative"
    else:
        # For other strategies, chunk_size and overlap are used, so validate them strictly
        if chunk_size < MIN_CHUNK_SIZE:
            return False, f"Chunk size ({chunk_size}) is too small (minimum {MIN_CHUNK_SIZE} characters)"
        
        if chunk_size > MAX_CHUNK_SIZE:
            return False, f"Chunk size ({chunk_size}) is too large (maximum {MAX_CHUNK_SIZE} characters)"
        
        if chunk_overlap < 0:
            return False, "Chunk overlap cannot be negative"
        
        if chunk_overlap >= chunk_size:
            return False, f"Chunk overlap ({chunk_overlap}) must be less than chunk size ({chunk_size})"
    
    # Validate max_chunks for all strategies
    if max_chunks is not None and max_chunks <= 0:
        return False, "max_chunks must be a positive integer"
    
    return True, None


def validate_chunk_quality(chunks: List[str], strict_min_size: bool = True) -> Tuple[List[str], Dict[str, Any]]:
    """
    Validate chunk quality and filter out invalid chunks.
    
    Args:
        chunks: List of text chunks to validate
        strict_min_size: If True, filter chunks smaller than MIN_CHUNK_SIZE.
                        If False, only filter empty chunks (useful for line-based chunking).
    
    Returns: (valid_chunks, quality_metrics)
    """
    valid_chunks = []
    quality_metrics = {
        "total_chunks": len(chunks),
        "valid_chunks": 0,
        "filtered_chunks": 0,
        "avg_chunk_length": 0,
        "min_chunk_length": float('inf'),
        "max_chunk_length": 0,
        "empty_chunks": 0,
        "too_small_chunks": 0,
        "issues": []
    }
    
    if not chunks:
        quality_metrics["issues"].append("No chunks generated")
        return [], quality_metrics
    
    total_length = 0
    
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        chunk_length = len(chunk)
        
        # Check for empty chunks (always filter these)
        if chunk_length == 0:
            quality_metrics["empty_chunks"] += 1
            quality_metrics["filtered_chunks"] += 1
            quality_metrics["issues"].append(f"Chunk {i+1} is empty")
            continue
        
        # Check for chunks that are too small (only if strict_min_size is True)
        if strict_min_size:
            if chunk_length < MIN_CHUNK_SIZE:
                quality_metrics["too_small_chunks"] += 1
                quality_metrics["filtered_chunks"] += 1
                quality_metrics["issues"].append(f"Chunk {i+1} is too small ({chunk_length} chars, minimum {MIN_CHUNK_SIZE})")
                continue
            
            # Check if chunk is mostly whitespace (only if strict_min_size is True)
            non_whitespace = len(chunk) - len(chunk.replace(' ', '').replace('\n', '').replace('\t', ''))
            if non_whitespace < MIN_CHUNK_SIZE:
                quality_metrics["too_small_chunks"] += 1
                quality_metrics["filtered_chunks"] += 1
                quality_metrics["issues"].append(f"Chunk {i+1} contains mostly whitespace")
                continue
        
        # Valid chunk
        valid_chunks.append(chunk)
        quality_metrics["valid_chunks"] += 1
        total_length += chunk_length
        quality_metrics["min_chunk_length"] = min(quality_metrics["min_chunk_length"], chunk_length)
        quality_metrics["max_chunk_length"] = max(quality_metrics["max_chunk_length"], chunk_length)
    
    # Calculate average
    if quality_metrics["valid_chunks"] > 0:
        quality_metrics["avg_chunk_length"] = total_length / quality_metrics["valid_chunks"]
    else:
        quality_metrics["avg_chunk_length"] = 0
        quality_metrics["min_chunk_length"] = 0
        quality_metrics["issues"].append("No valid chunks after filtering")
    
    # Reset min to 0 if no valid chunks
    if quality_metrics["min_chunk_length"] == float('inf'):
        quality_metrics["min_chunk_length"] = 0
    
    return valid_chunks, quality_metrics


def calculate_content_hash(content: str) -> str:
    """Calculate SHA-256 hash of content for duplicate detection"""
    normalized = unicodedata.normalize('NFC', content)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def normalize_content_for_comparison(content: str) -> str:
    """
    Normalize content for duplicate comparison.
    Removes extra whitespace and normalizes unicode.
    """
    # Normalize unicode
    normalized = unicodedata.normalize('NFC', content)
    
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Strip leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def detect_duplicate_content(content: str, existing_hashes: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Detect if content is a duplicate of existing content.
    Returns: (is_duplicate, matching_hash)
    """
    normalized = normalize_content_for_comparison(content)
    content_hash = calculate_content_hash(normalized)
    
    if content_hash in existing_hashes:
        return True, content_hash
    
    return False, None


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and invalid characters"""
    # Remove path components
    filename = Path(filename).name
    
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Limit length
    if len(sanitized) > 255:
        name, ext = Path(sanitized).stem, Path(sanitized).suffix
        sanitized = name[:255-len(ext)] + ext
    
    return sanitized or "unnamed_file"


def estimate_processing_time(content_length: int, chunk_size: int) -> Dict[str, Any]:
    """
    Estimate processing time based on content length and chunk size.
    Returns estimated metrics.
    """
    # Rough estimates (can be calibrated based on actual performance)
    estimated_chunks = max(1, content_length // chunk_size)
    
    # Time estimates (in seconds)
    chunking_time = estimated_chunks * 0.01  # 10ms per chunk
    embedding_time = estimated_chunks * 0.05  # 50ms per chunk (depends on model)
    storage_time = estimated_chunks * 0.02  # 20ms per chunk
    
    total_time = chunking_time + embedding_time + storage_time
    
    return {
        "estimated_chunks": estimated_chunks,
        "estimated_chunking_time": chunking_time,
        "estimated_embedding_time": embedding_time,
        "estimated_storage_time": storage_time,
        "estimated_total_time": total_time
    }

