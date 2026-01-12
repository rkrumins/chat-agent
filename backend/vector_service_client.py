"""
Vector Service Client for Backend.
Handles communication with the vector-service via REST API.
"""

import os
import logging
from typing import Dict, Any, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Configuration
VECTOR_SERVICE_URL = os.getenv("VECTOR_SERVICE_URL", "http://localhost:8003")


class VectorServiceClient:
    """Client for communicating with the vector-service microservice."""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or VECTOR_SERVICE_URL
        self.timeout = 30.0
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of vector service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    timeout=5.0
                )
                return response.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
    
    # Collection operations
    
    async def list_collections(self) -> Dict[str, Any]:
        """List all collections."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to list collections: {response.status_code}")
    
    async def create_collection(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new collection."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/collections",
                json={
                    "name": name,
                    "description": description,
                    "metadata": metadata or {}
                },
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to create collection: {response.text}")
    
    async def delete_collection(self, name: str) -> Dict[str, Any]:
        """Delete a collection."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/collections/{name}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise ValueError(f"Collection '{name}' not found")
            raise Exception(f"Failed to delete collection: {response.status_code}")
    
    async def get_collection_stats(self, name: str) -> Dict[str, Any]:
        """Get collection statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections/{name}/stats",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to get collection stats: {response.status_code}")
    
    # Document operations
    
    async def list_documents(
        self,
        collection_name: str,
        skip: int = 0,
        limit: int = 100,
        include_chunks: bool = False
    ) -> Dict[str, Any]:
        """List documents in a collection."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections/{collection_name}/documents",
                params={"skip": skip, "limit": limit, "include_chunks": include_chunks},
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise ValueError(f"Collection '{collection_name}' not found")
            raise Exception(f"Failed to list documents: {response.status_code}")
    
    async def get_document(
        self,
        collection_name: str,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific document."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections/{collection_name}/documents/{document_id}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            raise Exception(f"Failed to get document: {response.status_code}")
    
    async def delete_document(
        self,
        collection_name: str,
        document_id: str
    ) -> Dict[str, Any]:
        """Delete a document and its chunks."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/collections/{collection_name}/documents/{document_id}",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise ValueError(f"Document '{document_id}' not found")
            raise Exception(f"Failed to delete document: {response.status_code}")
    
    async def get_document_chunks(
        self,
        collection_name: str,
        document_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get chunks for a document."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections/{collection_name}/documents/{document_id}/chunks",
                params={"skip": skip, "limit": limit},
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to get document chunks: {response.status_code}")
    
    async def bulk_delete_documents(
        self,
        collection_name: str,
        document_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete multiple documents."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/collections/{collection_name}/documents/bulk-delete",
                json={"document_ids": document_ids},
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to bulk delete: {response.status_code}")
    
    # Search operations
    
    async def search(
        self,
        collection_name: str,
        query: str,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search for similar documents."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/collections/{collection_name}/search",
                json={
                    "query": query,
                    "n_results": n_results,
                    "where": where,
                    "include_content": True,
                    "include_metadata": True,
                    "include_distances": True
                },
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to search: {response.status_code}")
    
    # Tags operations
    
    async def get_collection_tags(self, collection_name: str) -> Dict[str, Any]:
        """Get all tags in a collection."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/collections/{collection_name}/tags",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to get tags: {response.status_code}")
    
    async def get_all_tags(self) -> Dict[str, Any]:
        """Get all tags across all collections."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/tags",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to get all tags: {response.status_code}")
    
    # Analytics
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get overall statistics."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/analytics/stats",
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json()
            raise Exception(f"Failed to get stats: {response.status_code}")


# Lazy initialization
_vector_client: Optional[VectorServiceClient] = None


def get_vector_client() -> VectorServiceClient:
    """Get the singleton vector service client."""
    global _vector_client
    if _vector_client is None:
        _vector_client = VectorServiceClient()
    return _vector_client
