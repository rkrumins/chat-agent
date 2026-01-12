"""
Abstract base class for vector database backends.
Defines the interface that all backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

import sys
import os
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared_schemas import CollectionResponse
from shared_schemas.vector import (
    VectorDocument, VectorStoreResponse, VectorSearchResponse,
)
from shared_schemas.collections import CollectionStatsResponse


class VectorBackend(ABC):
    """Abstract base class for vector database backends."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the backend connection."""
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """Cleanup and close connections."""
        pass
    
    # Collection operations
    
    @abstractmethod
    async def create_collection(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> CollectionResponse:
        """Create a new collection."""
        pass
    
    @abstractmethod
    async def get_collection(self, name: str) -> Optional[CollectionResponse]:
        """Get collection by name."""
        pass
    
    @abstractmethod
    async def list_collections(self) -> List[CollectionResponse]:
        """List all collections."""
        pass
    
    @abstractmethod
    async def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        pass
    
    @abstractmethod
    async def get_collection_stats(self, name: str) -> CollectionStatsResponse:
        """Get statistics for a collection."""
        pass
    
    # Document operations
    
    @abstractmethod
    async def store_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        generate_embeddings: bool = True
    ) -> VectorStoreResponse:
        """Store documents in a collection."""
        pass
    
    @abstractmethod
    async def get_document(
        self,
        collection_name: str,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID."""
        pass
    
    @abstractmethod
    async def list_documents(
        self,
        collection_name: str,
        skip: int = 0,
        limit: int = 100,
        include_chunks: bool = False
    ) -> Dict[str, Any]:
        """List documents in a collection."""
        pass
    
    @abstractmethod
    async def delete_document(
        self,
        collection_name: str,
        document_id: str
    ) -> None:
        """Delete a document and its chunks."""
        pass
    
    @abstractmethod
    async def delete_documents(
        self,
        collection_name: str,
        document_ids: List[str]
    ) -> int:
        """Delete multiple documents. Returns count of deleted."""
        pass
    
    @abstractmethod
    async def get_document_chunks(
        self,
        collection_name: str,
        document_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get chunks for a document."""
        pass
    
    # Search operations
    
    @abstractmethod
    async def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
        include_content: bool = True,
        include_metadata: bool = True,
        include_distances: bool = True
    ) -> VectorSearchResponse:
        """Search for similar documents."""
        pass
    
    # Tag operations
    
    @abstractmethod
    async def get_tags(self, collection_name: str) -> Dict[str, Any]:
        """Get all unique tags in a collection."""
        pass
    
    # Analytics
    
    @abstractmethod
    async def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall statistics across all collections."""
        pass
