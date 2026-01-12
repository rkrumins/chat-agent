"""
Collection-related Pydantic models.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from .base import EmbeddingProvider


class EmbeddingConfig(BaseModel):
    """Configuration for embedding model."""
    provider: str = Field(default="sentence-transformers", description="Embedding provider")
    model: Optional[str] = Field(default=None, description="Model name (None uses provider default)")
    dimension: Optional[int] = Field(default=None, description="Embedding dimension (auto-detected if None)")


class CollectionCreate(BaseModel):
    """Request to create a new collection."""
    name: str = Field(..., min_length=3, max_length=512, description="Collection name")
    description: Optional[str] = Field(default="", description="Collection description")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    embedding_config: Optional[EmbeddingConfig] = Field(default=None, description="Embedding configuration")


class CollectionConfig(BaseModel):
    """Collection configuration including embedding settings."""
    name: str
    description: str = ""
    embedding_provider: str = "sentence-transformers"
    embedding_model: Optional[str] = None
    embedding_dimension: int = 768
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CollectionResponse(BaseModel):
    """Response containing collection data."""
    name: str = Field(..., description="Collection name")
    id: str = Field(..., description="Collection ID")
    metadata: Dict[str, Any] = Field(..., description="Collection metadata including embedding info")
    count: int = Field(..., description="Number of documents in collection")


class CollectionListResponse(BaseModel):
    """Response containing list of collections."""
    collections: List[CollectionResponse]


class CollectionStatsResponse(BaseModel):
    """Response containing collection statistics."""
    name: str
    document_count: int = Field(..., description="Number of documents (not chunks)")
    chunk_count: int = Field(..., description="Number of chunks")
    metadata: Dict[str, Any] = Field(default_factory=dict)
