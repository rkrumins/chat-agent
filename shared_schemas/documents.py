"""
Document-related Pydantic models.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Metadata associated with a document."""
    name: str = Field(..., description="Document name/title")
    purpose: Optional[str] = Field(default="", description="Purpose or description of the document")
    tags: Optional[str] = Field(default="", description="Comma-separated tags")
    document_type: Optional[str] = Field(default=None, description="Document type: book, definition, article, blog_post, poem, unknown")
    custom_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional custom metadata")


class DocumentCreate(BaseModel):
    """Request to create a new document."""
    collection_name: str = Field(..., description="Target collection name")
    metadata: DocumentMetadata = Field(..., description="Document metadata")
    content: Optional[str] = Field(default="", description="Document text content (for text-based creation)")
    chunk_size: Optional[int] = Field(default=1000, ge=50, le=10000, description="Target chunk size in characters")
    chunk_overlap: Optional[int] = Field(default=200, ge=0, le=1000, description="Overlap between chunks")
    chunking_strategy: Optional[str] = Field(default="semantic", description="Chunking strategy to use")
    chunk_separator: Optional[str] = Field(default=None, description="Custom separator for 'custom' strategy")
    max_chunks: Optional[int] = Field(default=None, ge=1, description="Maximum number of chunks to create")
    create_new_version: Optional[bool] = Field(default=False, description="If True, create new version of existing doc")


class DocumentUpdate(BaseModel):
    """Request to update an existing document."""
    metadata: Optional[DocumentMetadata] = Field(default=None, description="Updated metadata")
    content: Optional[str] = Field(default=None, description="Updated content (triggers re-chunking)")
    chunk_size: Optional[int] = Field(default=None, ge=50, le=10000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=1000)
    chunking_strategy: Optional[str] = Field(default=None)
    chunk_separator: Optional[str] = Field(default=None)
    max_chunks: Optional[int] = Field(default=None, ge=1)


class DocumentResponse(BaseModel):
    """Response containing document data."""
    id: str = Field(..., description="Document ID")
    collection_name: str = Field(..., description="Collection containing this document")
    metadata: Dict[str, Any] = Field(..., description="Document metadata")
    content: str = Field(..., description="Full document content")
    created_at: str = Field(..., description="ISO timestamp of creation")
    updated_at: str = Field(..., description="ISO timestamp of last update")
    version: Optional[int] = Field(default=1, description="Document version number")


class ChunkMetadata(BaseModel):
    """Metadata for a document chunk."""
    chunk_index: int = Field(..., description="Zero-based chunk index")
    chunk_number: int = Field(..., description="One-based chunk number for display")
    total_chunks: int = Field(..., description="Total number of chunks in document")
    parent_id: str = Field(..., description="ID of parent document")
    parent_name: str = Field(..., description="Name of parent document")
    document_type: Optional[str] = Field(default="unknown")
    is_chunk: bool = Field(default=True)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ChunkResponse(BaseModel):
    """Response containing chunk data."""
    id: str = Field(..., description="Chunk ID")
    content: str = Field(..., description="Chunk text content")
    metadata: Dict[str, Any] = Field(..., description="Chunk metadata")
    chunk_number: int = Field(..., description="One-based chunk number")
    total_chunks: int = Field(..., description="Total chunks in parent document")
    chunk_index: int = Field(..., description="Zero-based chunk index")
    document_type: str = Field(default="unknown")
    parent_id: str = Field(..., description="Parent document ID")
    parent_name: str = Field(..., description="Parent document name")
    length: int = Field(..., description="Character count")
    word_count: int = Field(..., description="Word count")
