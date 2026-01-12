"""
Vector Service - Standalone microservice for vector database operations.
Provides abstraction layer for multiple vector database backends.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Add parent directory to path for shared_schemas import
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared_schemas import (
    CollectionCreate, CollectionResponse,
    VectorDBType, EmbeddingProvider,
)
from shared_schemas.vector import (
    VectorStoreRequest, VectorStoreResponse,
    VectorSearchRequest, VectorSearchResponse, VectorSearchResult,
    VectorDeleteRequest, VectorDeleteResponse,
    VectorGetRequest, VectorGetResponse, VectorDocument,
    VectorHealthResponse,
)
from shared_schemas.collections import (
    CollectionListResponse, CollectionStatsResponse, CollectionConfig,
)

from backends.chromadb_backend import ChromaDBBackend
from embedding import get_embedding_function
from job_queue import get_job_queue
from job_models import JobStatus, VectorJobCreate, VectorJobResponse, VectorJobStatus
from worker import init_worker, stop_worker, get_worker

# Configuration
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chromadb")
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", None)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global backend instance
vector_backend = None
embedding_function = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global vector_backend, embedding_function
    
    logger.info(f"Initializing vector service with backend: {VECTOR_BACKEND}")
    
    # Initialize embedding function
    embedding_function = get_embedding_function(
        provider=EMBEDDING_PROVIDER,
        model_name=EMBEDDING_MODEL
    )
    
    # Initialize vector backend
    if VECTOR_BACKEND == "chromadb":
        vector_backend = ChromaDBBackend(
            persist_path=CHROMA_DB_PATH,
            embedding_function=embedding_function
        )
    else:
        raise ValueError(f"Unsupported vector backend: {VECTOR_BACKEND}")
    
    await vector_backend.initialize()
    logger.info("Vector service initialized successfully")
    
    # Initialize and start background worker
    init_worker(vector_backend, embedding_function)
    logger.info("Background worker started")
    
    yield
    
    # Cleanup
    stop_worker()
    logger.info("Background worker stopped")
    
    if vector_backend:
        await vector_backend.cleanup()
    logger.info("Vector service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Vector Database Service",
    description="Microservice for vector database operations with pluggable backends",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "vector-service",
        "status": "running",
        "backend": VECTOR_BACKEND
    }


@app.get("/health", response_model=VectorHealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        collections = await vector_backend.list_collections()
        return VectorHealthResponse(
            status="healthy",
            service="vector-service",
            timestamp=datetime.utcnow(),
            backend=VECTOR_BACKEND,
            collections_count=len(collections)
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return VectorHealthResponse(
            status="unhealthy",
            service="vector-service",
            timestamp=datetime.utcnow(),
            backend=VECTOR_BACKEND,
            collections_count=0
        )


# ============================================================================
# Collection Endpoints
# ============================================================================

@app.get("/collections", response_model=CollectionListResponse)
async def list_collections():
    """List all collections."""
    try:
        collections = await vector_backend.list_collections()
        return CollectionListResponse(collections=collections)
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections", response_model=CollectionResponse)
async def create_collection(request: CollectionCreate):
    """Create a new collection."""
    try:
        collection = await vector_backend.create_collection(
            name=request.name,
            description=request.description,
            metadata=request.metadata or {}
        )
        return collection
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}", response_model=CollectionResponse)
async def get_collection(collection_name: str):
    """Get collection details."""
    try:
        collection = await vector_backend.get_collection(collection_name)
        if not collection:
            raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found")
        return collection
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete a collection."""
    try:
        await vector_backend.delete_collection(collection_name)
        return {"message": f"Collection '{collection_name}' deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/stats", response_model=CollectionStatsResponse)
async def get_collection_stats(collection_name: str):
    """Get collection statistics."""
    try:
        stats = await vector_backend.get_collection_stats(collection_name)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting collection stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Document Endpoints
# ============================================================================

@app.post("/collections/{collection_name}/documents", response_model=VectorStoreResponse)
async def store_documents(collection_name: str, request: VectorStoreRequest):
    """Store documents in a collection."""
    try:
        result = await vector_backend.store_documents(
            collection_name=collection_name,
            documents=request.documents,
            generate_embeddings=request.generate_embeddings
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error storing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents")
async def list_documents(
    collection_name: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    include_chunks: bool = Query(False)
):
    """List documents in a collection."""
    try:
        documents = await vector_backend.list_documents(
            collection_name=collection_name,
            skip=skip,
            limit=limit,
            include_chunks=include_chunks
        )
        return documents
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}")
async def get_document(collection_name: str, document_id: str):
    """Get a specific document."""
    try:
        document = await vector_backend.get_document(
            collection_name=collection_name,
            document_id=document_id
        )
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return document
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(collection_name: str, document_id: str):
    """Delete a document and its chunks."""
    try:
        await vector_backend.delete_document(
            collection_name=collection_name,
            document_id=document_id
        )
        return {"message": f"Document '{document_id}' deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}/chunks")
async def get_document_chunks(
    collection_name: str,
    document_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get all chunks for a document."""
    try:
        chunks = await vector_backend.get_document_chunks(
            collection_name=collection_name,
            document_id=document_id,
            skip=skip,
            limit=limit
        )
        return chunks
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting document chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents/bulk-delete", response_model=VectorDeleteResponse)
async def bulk_delete_documents(collection_name: str, request: VectorDeleteRequest):
    """Delete multiple documents."""
    try:
        result = await vector_backend.delete_documents(
            collection_name=collection_name,
            document_ids=request.document_ids
        )
        return VectorDeleteResponse(
            deleted_count=result,
            collection_name=collection_name
        )
    except Exception as e:
        logger.error(f"Error bulk deleting documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Search Endpoints
# ============================================================================

@app.post("/collections/{collection_name}/search", response_model=VectorSearchResponse)
async def search_documents(collection_name: str, request: VectorSearchRequest):
    """Search for similar documents."""
    try:
        results = await vector_backend.search(
            collection_name=collection_name,
            query=request.query,
            n_results=request.n_results,
            where=request.where,
            include_content=request.include_content,
            include_metadata=request.include_metadata,
            include_distances=request.include_distances
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        # Check for embedding dimension mismatch
        if "dimension" in str(e).lower():
            return VectorSearchResponse(
                query=request.query,
                results=[],
                count=0,
                warning="Embedding dimension mismatch. Collection may need to be re-indexed."
            )
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tag Endpoints
# ============================================================================

@app.get("/collections/{collection_name}/tags")
async def get_collection_tags(collection_name: str):
    """Get all unique tags in a collection."""
    try:
        tags = await vector_backend.get_tags(collection_name)
        return tags
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tags")
async def get_all_tags():
    """Get all unique tags across all collections."""
    try:
        all_tags = {}
        collections = await vector_backend.list_collections()
        
        for col in collections:
            tags = await vector_backend.get_tags(col.name)
            for tag_info in tags.get("tags", []):
                tag = tag_info["tag"]
                count = tag_info["count"]
                all_tags[tag] = all_tags.get(tag, 0) + count
        
        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
        return {
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
            "total": len(sorted_tags)
        }
    except Exception as e:
        logger.error(f"Error getting all tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Analytics Endpoints
# ============================================================================

@app.get("/analytics/stats")
async def get_stats():
    """Get overall system statistics."""
    try:
        stats = await vector_backend.get_overall_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Async Job Endpoints (Background Processing)
# ============================================================================

@app.post("/jobs", response_model=VectorJobResponse)
async def submit_job(request: VectorJobCreate):
    """
    Submit documents for async background processing.
    Returns immediately with a job ID for status tracking.
    """
    try:
        queue = get_job_queue()
        
        job_id = queue.enqueue(
            collection_name=request.collection_name,
            documents=[doc.model_dump() if hasattr(doc, 'model_dump') else doc for doc in request.documents],
            callback_url=request.callback_url,
            batch_size=request.batch_size
        )
        
        return VectorJobResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            message="Job queued for background processing",
            total_documents=len(request.documents)
        )
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs")
async def list_jobs(status: str = None, limit: int = 50):
    """List recent jobs and worker pool status."""
    try:
        queue = get_job_queue()
        pending = queue.get_pending_count()
        
        worker_pool = get_worker()
        if worker_pool:
            pool_status = worker_pool.get_status()
        else:
            pool_status = {"num_workers": 0, "active_workers": 0, "running": False}
        
        return {
            "pending_jobs": pending,
            "worker_pool": pool_status,
            "message": "Use GET /jobs/{job_id} to check specific job status"
        }
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# IMPORTANT: These specific routes must come BEFORE /jobs/{job_id}
@app.get("/jobs/history")
async def get_job_history(
    status: str = Query(None, description="Filter by status: pending, processing, completed, failed, cancelled"),
    limit: int = Query(50, ge=1, le=200, description="Max jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
    order_by: str = Query("created_at", description="Order by: created_at, started_at, completed_at")
):
    """
    Get full job history with filtering and pagination.
    Persisted across service restarts.
    """
    try:
        queue = get_job_queue()
        result = queue.list_jobs(
            status=status,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_desc=True
        )
        return result
    except Exception as e:
        logger.error(f"Error getting job history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/stats")
async def get_job_stats():
    """Get job statistics by status."""
    try:
        queue = get_job_queue()
        stats = queue.get_job_stats()
        
        worker_pool = get_worker()
        if worker_pool:
            stats["worker_pool"] = worker_pool.get_status()
        
        return stats
    except Exception as e:
        logger.error(f"Error getting job stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/jobs/cleanup")
async def cleanup_old_jobs(days: int = Query(7, ge=1, le=365, description="Delete jobs older than X days")):
    """Clean up old completed/failed/cancelled jobs."""
    try:
        queue = get_job_queue()
        deleted = queue.cleanup_old_jobs(days=days)
        return {"deleted": deleted, "message": f"Cleaned up jobs older than {days} days"}
    except Exception as e:
        logger.error(f"Error cleaning up jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Parameterized routes must come AFTER specific routes
@app.get("/jobs/{job_id}", response_model=VectorJobStatus)
async def get_job_status(job_id: str):
    """Get the status of a background processing job."""
    try:
        queue = get_job_queue()
        job = queue.get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return VectorJobStatus(
            job_id=job['id'],
            status=JobStatus(job['status']),
            collection_name=job['collection_name'],
            total_documents=job['total_documents'],
            processed_count=job['processed_count'],
            progress_percent=job['progress_percent'],
            error_message=job.get('error_message'),
            created_at=job['created_at'],
            started_at=job.get('started_at'),
            completed_at=job.get('completed_at')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Cancel a pending job."""
    try:
        queue = get_job_queue()
        cancelled = queue.cancel_job(job_id)
        
        if cancelled:
            return {"message": f"Job {job_id} cancelled", "cancelled": True}
        else:
            return {"message": f"Job {job_id} could not be cancelled (may already be processing)", "cancelled": False}
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
