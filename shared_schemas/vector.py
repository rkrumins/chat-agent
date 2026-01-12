"""
Vector service related Pydantic models.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class VectorDocument(BaseModel):
    """A document to store in the vector database."""
    id: str = Field(..., description="Unique document/chunk ID")
    content: str = Field(..., description="Text content")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Document metadata")
    embedding: Optional[List[float]] = Field(default=None, description="Pre-computed embedding (optional)")


class VectorStoreRequest(BaseModel):
    """Request to store documents in vector database."""
    collection_name: str = Field(..., description="Target collection")
    documents: List[VectorDocument] = Field(..., description="Documents to store")
    generate_embeddings: bool = Field(default=True, description="Generate embeddings if not provided")


class VectorStoreResponse(BaseModel):
    """Response after storing documents."""
    stored_count: int = Field(..., description="Number of documents stored")
    collection_name: str
    document_ids: List[str] = Field(..., description="IDs of stored documents")


class VectorSearchRequest(BaseModel):
    """Request to search for similar documents."""
    query: str = Field(..., description="Search query text")
    n_results: int = Field(default=5, ge=1, le=100, description="Number of results to return")
    where: Optional[Dict[str, Any]] = Field(default=None, description="Metadata filter")
    include_content: bool = Field(default=True, description="Include document content in results")
    include_metadata: bool = Field(default=True, description="Include metadata in results")
    include_distances: bool = Field(default=True, description="Include similarity distances")


class VectorSearchResult(BaseModel):
    """A single search result."""
    id: str = Field(..., description="Document/chunk ID")
    content: Optional[str] = Field(default=None, description="Document content")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Document metadata")
    distance: Optional[float] = Field(default=None, description="Distance/similarity score")


class VectorSearchResponse(BaseModel):
    """Response containing search results."""
    query: str
    results: List[VectorSearchResult]
    count: int
    warning: Optional[str] = Field(default=None, description="Warning message if any issues")


class VectorDeleteRequest(BaseModel):
    """Request to delete documents from vector database."""
    document_ids: List[str] = Field(..., description="IDs of documents to delete")


class VectorDeleteResponse(BaseModel):
    """Response after deleting documents."""
    deleted_count: int
    collection_name: str


class VectorGetRequest(BaseModel):
    """Request to get specific documents by ID."""
    document_ids: List[str] = Field(..., description="IDs of documents to retrieve")
    include_content: bool = Field(default=True)
    include_metadata: bool = Field(default=True)
    include_embeddings: bool = Field(default=False)


class VectorGetResponse(BaseModel):
    """Response containing requested documents."""
    documents: List[VectorDocument]
    count: int


class VectorHealthResponse(BaseModel):
    """Health check response for vector service."""
    status: str
    service: str = "vector-service"
    timestamp: datetime
    backend: str  # e.g., "chromadb"
    collections_count: int
