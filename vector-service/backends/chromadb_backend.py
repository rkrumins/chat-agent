"""
ChromaDB implementation of the VectorBackend interface.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

import chromadb
from chromadb.config import Settings

sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from shared_schemas import CollectionResponse
from shared_schemas.vector import (
    VectorDocument, VectorStoreResponse, VectorSearchResponse, VectorSearchResult,
)
from shared_schemas.collections import CollectionStatsResponse

from .base import VectorBackend

logger = logging.getLogger(__name__)


class ChromaDBBackend(VectorBackend):
    """ChromaDB implementation of the vector backend."""
    
    def __init__(
        self,
        persist_path: str = "./chroma_db",
        embedding_function = None
    ):
        self.persist_path = persist_path
        self.embedding_function = embedding_function
        self.client = None
    
    async def initialize(self) -> None:
        """Initialize ChromaDB client."""
        logger.info(f"Initializing ChromaDB with path: {self.persist_path}")
        self.client = chromadb.PersistentClient(path=self.persist_path)
        logger.info("ChromaDB initialized successfully")
    
    async def cleanup(self) -> None:
        """Cleanup ChromaDB connection."""
        # ChromaDB PersistentClient doesn't need explicit cleanup
        logger.info("ChromaDB cleanup complete")
    
    def _prepare_metadata_for_chroma(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare metadata for ChromaDB - convert lists/dicts to strings."""
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
    
    # Collection operations
    
    async def create_collection(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> CollectionResponse:
        """Create a new collection."""
        try:
            # Get embedding info
            embedding_provider = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
            embedding_model = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")
            
            # Get embedding dimension
            embedding_dimension = 768  # Default
            if self.embedding_function:
                try:
                    test_result = self.embedding_function(["test"])
                    embedding_dimension = len(test_result[0]) if test_result else 768
                except Exception:
                    pass
            
            collection_metadata = {
                "description": description,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
                "embedding_dimension": embedding_dimension,
                "created_at": datetime.utcnow().isoformat(),
                **(metadata or {})
            }
            
            col = self.client.create_collection(
                name=name,
                metadata=collection_metadata,
                embedding_function=self.embedding_function
            )
            
            return CollectionResponse(
                name=col.name,
                id=str(col.id),
                metadata=col.metadata or {},
                count=0
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                raise ValueError(f"Collection '{name}' already exists")
            raise
    
    async def get_collection(self, name: str) -> Optional[CollectionResponse]:
        """Get collection by name."""
        try:
            col = self.client.get_collection(
                name=name,
                embedding_function=self.embedding_function
            )
            count = col.count()
            
            # Count only documents (not chunks)
            all_items = col.get(include=["metadatas"])
            doc_count = sum(
                1 for m in (all_items.get("metadatas") or [])
                if not m.get("is_chunk", False)
            )
            
            return CollectionResponse(
                name=col.name,
                id=str(col.id),
                metadata=col.metadata or {},
                count=doc_count
            )
        except Exception as e:
            if "does not exist" in str(e).lower():
                return None
            raise
    
    async def list_collections(self) -> List[CollectionResponse]:
        """List all collections."""
        collections = self.client.list_collections()
        result = []
        
        for col in collections:
            try:
                all_items = col.get(include=["metadatas"])
                doc_count = sum(
                    1 for m in (all_items.get("metadatas") or [])
                    if not m.get("is_chunk", False)
                )
            except Exception:
                doc_count = col.count()
            
            result.append(CollectionResponse(
                name=col.name,
                id=str(col.id),
                metadata=col.metadata or {},
                count=doc_count
            ))
        
        return result
    
    async def delete_collection(self, name: str) -> None:
        """Delete a collection."""
        try:
            self.client.delete_collection(name=name)
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{name}' not found")
            raise
    
    async def get_collection_stats(self, name: str) -> CollectionStatsResponse:
        """Get statistics for a collection."""
        try:
            col = self.client.get_collection(
                name=name,
                embedding_function=self.embedding_function
            )
            all_items = col.get(include=["metadatas"])
            
            documents = [
                m for m in (all_items.get("metadatas") or [])
                if not m.get("is_chunk", False)
            ]
            chunks = [
                m for m in (all_items.get("metadatas") or [])
                if m.get("is_chunk", False)
            ]
            
            return CollectionStatsResponse(
                name=name,
                document_count=len(documents),
                chunk_count=len(chunks),
                metadata=col.metadata or {}
            )
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{name}' not found")
            raise
    
    # Document operations
    
    async def store_documents(
        self,
        collection_name: str,
        documents: List[VectorDocument],
        generate_embeddings: bool = True
    ) -> VectorStoreResponse:
        """Store documents in a collection."""
        try:
            col = self.client.get_or_create_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            ids = [doc.id for doc in documents]
            contents = [doc.content for doc in documents]
            metadatas = [self._prepare_metadata_for_chroma(doc.metadata) for doc in documents]
            
            if generate_embeddings or not documents[0].embedding:
                # Let ChromaDB generate embeddings
                col.add(
                    ids=ids,
                    documents=contents,
                    metadatas=metadatas
                )
            else:
                # Use provided embeddings
                embeddings = [doc.embedding for doc in documents]
                col.add(
                    ids=ids,
                    documents=contents,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
            
            return VectorStoreResponse(
                stored_count=len(documents),
                collection_name=collection_name,
                document_ids=ids
            )
        except Exception as e:
            logger.error(f"Error storing documents: {e}")
            raise
    
    async def get_document(
        self,
        collection_name: str,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID."""
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            result = col.get(
                ids=[document_id],
                include=["documents", "metadatas"]
            )
            
            if not result["ids"]:
                return None
            
            metadata = result["metadatas"][0] if result["metadatas"] else {}
            content = result["documents"][0] if result["documents"] else ""
            
            return {
                "id": document_id,
                "collection_name": collection_name,
                "metadata": metadata,
                "content": content,
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", "")
            }
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    async def list_documents(
        self,
        collection_name: str,
        skip: int = 0,
        limit: int = 100,
        include_chunks: bool = False
    ) -> Dict[str, Any]:
        """List documents in a collection."""
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            all_results = col.get(include=["documents", "metadatas"])
            
            documents = []
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                
                # Skip chunks unless requested
                if not include_chunks and metadata.get("is_chunk") is True:
                    continue
                
                # Skip old versions
                if metadata.get("is_latest") is False:
                    continue
                
                content = all_results["documents"][i] if all_results["documents"] else ""
                
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
            total = len(documents)
            paginated = documents[skip:skip + limit]
            
            return {
                "documents": paginated,
                "total": total,
                "skip": skip,
                "limit": limit
            }
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    async def delete_document(
        self,
        collection_name: str,
        document_id: str
    ) -> None:
        """Delete a document and its chunks."""
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            # Find and delete chunks
            all_results = col.get(include=["metadatas"])
            chunk_ids = []
            
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                if metadata.get("parent_id") == document_id and metadata.get("is_chunk") is True:
                    chunk_ids.append(doc_id)
            
            if chunk_ids:
                col.delete(ids=chunk_ids)
                logger.info(f"Deleted {len(chunk_ids)} chunks for document {document_id}")
            
            # Delete main document
            try:
                col.delete(ids=[document_id])
            except Exception:
                pass  # Document might not exist if only chunks were stored
            
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    async def delete_documents(
        self,
        collection_name: str,
        document_ids: List[str]
    ) -> int:
        """Delete multiple documents. Returns count of deleted."""
        deleted = 0
        for doc_id in document_ids:
            try:
                await self.delete_document(collection_name, doc_id)
                deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete document {doc_id}: {e}")
        return deleted
    
    async def get_document_chunks(
        self,
        collection_name: str,
        document_id: str,
        skip: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get chunks for a document."""
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            all_results = col.get(include=["documents", "metadatas"])
            
            chunks = []
            for i, chunk_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                
                if metadata.get("is_chunk") is not True:
                    continue
                
                parent_id = metadata.get("parent_id")
                belongs = (
                    parent_id == document_id or
                    chunk_id.startswith(f"{document_id}_chunk_")
                )
                
                if belongs:
                    content = all_results["documents"][i] if all_results["documents"] else ""
                    
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
                        "length": len(content),
                        "word_count": len(content.split()) if content else 0
                    })
            
            # Sort by chunk_number
            chunks.sort(key=lambda x: x.get("chunk_number", 0))
            
            total = len(chunks)
            paginated = chunks[skip:skip + limit]
            
            return {
                "chunks": paginated,
                "total": total,
                "skip": skip,
                "limit": limit,
                "document_id": document_id
            }
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    # Search operations
    
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
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            include = []
            if include_content:
                include.append("documents")
            if include_metadata:
                include.append("metadatas")
            if include_distances:
                include.append("distances")
            
            results = col.query(
                query_texts=[query],
                n_results=n_results,
                where=where,
                include=include
            )
            
            search_results = []
            if results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    search_results.append(VectorSearchResult(
                        id=results["ids"][0][i],
                        content=results["documents"][0][i] if results.get("documents") else None,
                        metadata=results["metadatas"][0][i] if results.get("metadatas") else None,
                        distance=results["distances"][0][i] if results.get("distances") else None
                    ))
            
            return VectorSearchResponse(
                query=query,
                results=search_results,
                count=len(search_results)
            )
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    # Tag operations
    
    async def get_tags(self, collection_name: str) -> Dict[str, Any]:
        """Get all unique tags in a collection."""
        try:
            col = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            
            all_items = col.get(include=["metadatas"])
            
            tag_counts = {}
            for metadata in all_items.get("metadatas", []):
                if metadata.get("is_chunk", False):
                    continue
                
                tags_str = metadata.get("tags", "")
                if tags_str:
                    tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
                    for tag in tags:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            
            return {
                "collection": collection_name,
                "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
                "total": len(sorted_tags)
            }
        except Exception as e:
            if "does not exist" in str(e).lower():
                raise ValueError(f"Collection '{collection_name}' not found")
            raise
    
    # Analytics
    
    async def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall statistics across all collections."""
        collections = self.client.list_collections()
        
        total_documents = 0
        total_chunks = 0
        collection_details = []
        
        for col in collections:
            try:
                chroma_col = self.client.get_collection(
                    name=col.name,
                    embedding_function=self.embedding_function
                )
                all_items = chroma_col.get(include=["metadatas"])
                
                documents = [
                    m for m in (all_items.get("metadatas") or [])
                    if not m.get("is_chunk", False)
                ]
                chunks = [
                    m for m in (all_items.get("metadatas") or [])
                    if m.get("is_chunk", False)
                ]
                
                doc_count = len(documents)
                chunk_count = len(chunks)
                
                total_documents += doc_count
                total_chunks += chunk_count
                
                collection_details.append({
                    "name": col.name,
                    "document_count": doc_count,
                    "chunk_count": chunk_count,
                    "metadata": col.metadata or {}
                })
            except Exception as e:
                logger.warning(f"Error getting stats for collection {col.name}: {e}")
        
        return {
            "total_collections": len(collections),
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "collections": collection_details
        }
