"""
Vector Service Client for Ingestion Service.
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
        self.timeout = 60.0  # Longer timeout for batch operations
    
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
    
    async def store_documents(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        generate_embeddings: bool = True
    ) -> Dict[str, Any]:
        """
        Store documents (chunks) in the vector database.
        
        Args:
            collection_name: Target collection
            documents: List of document dicts with id, content, metadata
            generate_embeddings: Whether to generate embeddings
            
        Returns:
            Response with stored_count and document_ids
        """
        payload = {
            "collection_name": collection_name,
            "documents": documents,
            "generate_embeddings": generate_embeddings
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/collections/{collection_name}/documents",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Failed to store documents: {response.status_code} - {response.text}")
                    raise Exception(f"Vector service returned {response.status_code}: {response.text}")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to vector service: {e}")
            raise Exception(f"Failed to connect to vector service at {self.base_url}: {e}")
    
    async def delete_document(
        self,
        collection_name: str,
        document_id: str
    ) -> Dict[str, Any]:
        """Delete a document and its chunks from the vector database."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/collections/{collection_name}/documents/{document_id}",
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    logger.warning(f"Document {document_id} not found in collection {collection_name}")
                    return {"message": "Document not found"}
                else:
                    raise Exception(f"Failed to delete document: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to delete document: {e}")
            raise
    
    async def get_or_create_collection(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Get a collection or create it if it doesn't exist."""
        try:
            async with httpx.AsyncClient() as client:
                # First try to get the collection
                response = await client.get(
                    f"{self.base_url}/collections/{name}",
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    # Create the collection
                    create_response = await client.post(
                        f"{self.base_url}/collections",
                        json={
                            "name": name,
                            "description": description,
                            "metadata": metadata or {}
                        },
                        timeout=self.timeout
                    )
                    
                    if create_response.status_code == 200:
                        return create_response.json()
                    else:
                        raise Exception(f"Failed to create collection: {create_response.text}")
                else:
                    raise Exception(f"Failed to get collection: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to get/create collection: {e}")
            raise
    
    async def bulk_delete_documents(
        self,
        collection_name: str,
        document_ids: List[str]
    ) -> Dict[str, Any]:
        """Delete multiple documents from a collection."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/collections/{collection_name}/documents/bulk-delete",
                    json={"document_ids": document_ids},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    raise Exception(f"Failed to bulk delete: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to bulk delete documents: {e}")
            raise


# Default client instance
vector_client = VectorServiceClient()
