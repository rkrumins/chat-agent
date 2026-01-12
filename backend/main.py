"""
Backend API Gateway - FastAPI service for VectorDB Management.
Orchestrates between frontend, ingestion-service, and vector-service.
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Add parent directory to path for shared_schemas
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import shared_schemas, fallback to local definitions
try:
    from shared_schemas import (
        ProcessingStatus, ChunkingStrategy,
        DocumentMetadata, DocumentCreate, DocumentUpdate,
    )
    USING_SHARED_SCHEMAS = True
except ImportError:
    USING_SHARED_SCHEMAS = False
    # Local definitions for backwards compatibility
    class ProcessingStatus(str, Enum):
        PENDING = "pending"
        PROCESSING = "processing"
        COMPLETED = "completed"
        FAILED = "failed"

    class ChunkingStrategy(str, Enum):
        SEMANTIC = "semantic"
        SIZE = "size"
        LINES = "lines"
        PARAGRAPHS = "paragraphs"
        SENTENCES = "sentences"
        CUSTOM = "custom"

from utils import (
    validate_file_size, validate_content, validate_chunking_parameters,
    validate_chunk_quality, calculate_content_hash, detect_duplicate_content,
    sanitize_filename, estimate_processing_time, MAX_FILE_SIZE
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
VECTOR_SERVICE_URL = os.getenv("VECTOR_SERVICE_URL", "http://localhost:8003")
INGESTION_SERVICE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8002")

# Lazy-loaded microservices components
_microservices_loaded = False
_get_db = None
_ingestion_client = None
_file_storage = None
_vector_client = None


def get_microservices():
    """
    Lazy loader for microservices components.
    Returns (get_db, ingestion_client, file_storage, vector_client, enabled).
    """
    global _microservices_loaded, _get_db, _ingestion_client, _file_storage, _vector_client
    
    if not _microservices_loaded:
        try:
            from config import get_db, StoredFile, FileCollectionLink
            from ingestion_client import IngestionClient, FileStorageManager
            from vector_service_client import VectorServiceClient
            
            _get_db = get_db
            _ingestion_client = IngestionClient()
            _file_storage = FileStorageManager()
            _vector_client = VectorServiceClient(base_url=VECTOR_SERVICE_URL)
            
            _microservices_loaded = True
            logger.info("Microservices components loaded successfully")
        except ImportError as e:
            logger.warning(f"Microservices not available: {e}")
            _microservices_loaded = True
    
    return _get_db, _ingestion_client, _file_storage, _vector_client, (_get_db is not None)


# Pydantic Models (keeping these for backward compatibility with frontend)

class DocumentMetadataLocal(BaseModel):
    name: str
    purpose: Optional[str] = ""
    tags: Optional[str] = ""
    document_type: Optional[str] = None
    custom_metadata: Optional[Dict[str, Any]] = {}


class DocumentCreateLocal(BaseModel):
    collection_name: str
    metadata: DocumentMetadataLocal
    content: Optional[str] = ""
    chunk_size: Optional[int] = 1000
    chunk_overlap: Optional[int] = 200
    chunking_strategy: Optional[str] = "semantic"
    chunk_separator: Optional[str] = None
    max_chunks: Optional[int] = None
    create_new_version: Optional[bool] = False


class DocumentUpdateLocal(BaseModel):
    metadata: Optional[DocumentMetadataLocal] = None
    content: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunking_strategy: Optional[str] = None
    chunk_separator: Optional[str] = None
    max_chunks: Optional[int] = None


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = {}


class CallbackPayload(BaseModel):
    """Payload received from ingestion service for status updates."""
    job_id: str
    status: str
    progress: int
    message: Optional[str] = None
    error: Optional[str] = None
    document_id: Optional[str] = None
    collection_name: Optional[str] = None
    document_type: Optional[str] = None
    chunks_created: Optional[int] = None
    timestamp: Optional[datetime] = None


class BulkDeleteRequest(BaseModel):
    document_ids: List[str]


class BulkUpdateTagsRequest(BaseModel):
    document_ids: List[str]
    tags: str
    mode: str = "replace"


# In-memory storage for processing status
processing_status: Dict[str, Dict[str, Any]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("Starting Backend API Gateway...")
    
    # Pre-load microservices
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if enabled:
        # Check vector service health
        if vector_client:
            health = await vector_client.health_check()
            if health.get("status") == "healthy":
                logger.info("Vector service is healthy")
            else:
                logger.warning(f"Vector service health: {health}")
    
    logger.info("Backend API Gateway started successfully")
    
    yield
    
    logger.info("Backend API Gateway shutting down...")


# Create FastAPI app
app = FastAPI(
    title="VectorDB Management API",
    version="2.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Root Endpoints
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "VectorDB Management API",
        "version": "2.0.0",
        "status": "running",
        "architecture": "microservices"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    vector_health = {"status": "not_configured"}
    if vector_client:
        vector_health = await vector_client.health_check()
    
    ingestion_health = {"status": "not_configured"}
    if ingestion_client:
        ingestion_health = await ingestion_client.health_check()
    
    return {
        "status": "healthy" if vector_health.get("status") == "healthy" else "degraded",
        "vector_service": vector_health,
        "ingestion_service": ingestion_health,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# Collection Endpoints - Delegate to Vector Service
# ============================================================================

@app.get("/collections")
async def list_collections():
    """List all collections."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.list_collections()
        return result
    except Exception as e:
        logger.error(f"Error listing collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections")
async def create_collection(collection: CollectionCreate):
    """Create a new collection."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.create_collection(
            name=collection.name,
            description=collection.description,
            metadata=collection.metadata or {}
        )
        return {
            **result,
            "message": "Collection created successfully"
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error creating collection: {error_msg}")
        
        if "already exists" in error_msg.lower():
            raise HTTPException(status_code=400, detail=f"Collection '{collection.name}' already exists")
        elif "validation" in error_msg.lower() or "name" in error_msg.lower():
            raise HTTPException(status_code=400, detail=(
                "Invalid collection name. Collection names must:\n"
                "• Be 3-512 characters long\n"
                "• Contain only letters, numbers, dots (.), underscores (_), and hyphens (-)\n"
                "• Start and end with a letter or number"
            ))
        
        raise HTTPException(status_code=400, detail=error_msg)


@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete a collection."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.delete_collection(collection_name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Document Endpoints
# ============================================================================

@app.get("/collections/{collection_name}/documents")
async def list_documents(
    collection_name: str, 
    skip: int = 0, 
    limit: int = 100,
    show_all_versions: bool = False
):
    """List all documents in a collection."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.list_documents(
            collection_name=collection_name,
            skip=skip,
            limit=limit,
            include_chunks=False
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}")
async def get_document(collection_name: str, document_id: str):
    """Get a specific document."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.get_document(
            collection_name=collection_name,
            document_id=document_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Document not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents")
async def create_document(
    collection_name: str,
    document: DocumentCreateLocal,
    background_tasks: BackgroundTasks
):
    """Create a new document from text (delegates to ingestion service)."""
    get_db, ingestion_client, file_storage, vector_client, microservices_enabled = get_microservices()
    
    if not microservices_enabled:
        raise HTTPException(status_code=503, detail="Microservices are not available")
    
    try:
        # Validate content
        if not document.content or not document.content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        
        if document.chunk_size and document.chunk_size < 50:
            raise HTTPException(status_code=400, detail="Chunk size should be at least 50 characters")
        
        # Create IDs
        document_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        
        # Prepare metadata
        metadata = {
            "name": document.metadata.name,
            "purpose": document.metadata.purpose or "",
            "tags": document.metadata.tags or "",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **(document.metadata.custom_metadata or {})
        }
        
        # Store content as file
        db = next(get_db())
        try:
            file_content = document.content.encode('utf-8')
            filename = f"{document.metadata.name}.txt"
            
            stored_file, collection_link, is_new = file_storage.store_file(
                file_content=file_content,
                original_filename=filename,
                collection_name=collection_name,
                document_id=document_id,
                db=db
            )
            
            db.commit()
            
            # Trigger ingestion
            await ingestion_client.trigger_ingestion(
                job_id=job_id,
                file_id=stored_file.id,
                file_path=str(file_storage.files_dir.parent / stored_file.storage_path),
                collection_name=collection_name,
                document_id=document_id,
                metadata=metadata,
                chunk_size=document.chunk_size or 1000,
                chunk_overlap=document.chunk_overlap or 200,
                chunking_strategy=document.chunking_strategy or "semantic",
                chunk_separator=document.chunk_separator,
                max_chunks=document.max_chunks,
                version=1,
                create_new_version=document.create_new_version
            )
            
        finally:
            db.close()
        
        # Initialize status
        processing_status[job_id] = {
            "task_id": job_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document queued for ingestion",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        return {
            "document_id": document_id,
            "task_id": job_id,
            "version": 1,
            "message": "Document queued for processing",
            "status": ProcessingStatus.PENDING
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents/upload")
async def upload_document(
    collection_name: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    purpose: str = Form(""),
    tags: str = Form(""),
    document_type: Optional[str] = Form(None),
    chunk_size: int = Form(1000),
    chunk_overlap: int = Form(200),
    chunking_strategy: str = Form("semantic"),
    chunk_separator: str = Form(None),
    max_chunks: int = Form(None),
    custom_metadata: str = Form("{}"),
    create_new_version: bool = Form(False),
    background_tasks: BackgroundTasks = None
):
    """Upload and process a document file via ingestion microservice."""
    get_db, ingestion_client, file_storage, vector_client, microservices_enabled = get_microservices()
    
    if not microservices_enabled:
        raise HTTPException(status_code=503, detail="Microservices are not available")
    
    try:
        # Read and validate file
        file_content = await file.read()
        file_size = len(file_content)
        
        is_valid, error_msg = validate_file_size(file_size)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Validate filename and extension
        sanitized_filename = sanitize_filename(file.filename)
        extension = Path(sanitized_filename).suffix.lower()
        supported_extensions = ['.pdf', '.docx', '.doc', '.txt', '.text', '.json']
        if extension not in supported_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {extension}. Supported: {', '.join(supported_extensions)}"
            )
        
        # Validate chunking parameters
        is_valid, error_msg = validate_chunking_parameters(
            chunk_size, chunk_overlap, chunking_strategy, max_chunks
        )
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        document_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Parse custom metadata
        try:
            custom_meta = json.loads(custom_metadata) if custom_metadata else {}
        except json.JSONDecodeError:
            custom_meta = {}
        
        # Prepare metadata
        metadata = {
            "name": name,
            "purpose": purpose,
            "tags": tags,
            "filename": sanitized_filename,
            "original_filename": file.filename,
            "file_type": extension,
            "file_size": file_size,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **custom_meta
        }
        
        # Handle max_chunks
        max_chunks_int = None
        if max_chunks is not None:
            try:
                max_chunks_int = int(max_chunks) if max_chunks != 0 else None
            except (ValueError, TypeError):
                max_chunks_int = None
        
        # Store file and trigger ingestion
        db = next(get_db())
        try:
            stored_file, collection_link, is_new = file_storage.store_file(
                file_content=file_content,
                original_filename=sanitized_filename,
                collection_name=collection_name,
                document_id=document_id,
                db=db
            )
            
            file_path = str(file_storage.get_file_path(stored_file))
            
            # Initialize status
            processing_status[task_id] = {
                "task_id": task_id,
                "document_id": document_id,
                "status": ProcessingStatus.PENDING,
                "message": "Document queued for ingestion",
                "progress": 0,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Trigger ingestion
            await ingestion_client.trigger_ingestion(
                job_id=task_id,
                file_id=stored_file.id,
                file_path=file_path,
                collection_name=collection_name,
                document_id=document_id,
                metadata=metadata,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                chunking_strategy=chunking_strategy or "semantic",
                chunk_separator=chunk_separator if chunk_separator and chunk_separator != "null" else None,
                max_chunks=max_chunks_int,
                document_type=document_type,
                version=1,
                create_new_version=create_new_version
            )
            
        finally:
            db.close()
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": 1,
            "message": "Document queued for processing",
            "status": ProcessingStatus.PENDING,
            "filename": file.filename
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/collections/{collection_name}/documents/{document_id}")
async def update_document(
    collection_name: str,
    document_id: str,
    update: DocumentUpdateLocal,
    background_tasks: BackgroundTasks
):
    """Update an existing document (delegates to ingestion service)."""
    get_db, ingestion_client, file_storage, vector_client, microservices_enabled = get_microservices()
    
    if not microservices_enabled:
        raise HTTPException(status_code=503, detail="Microservices are not available")
    
    try:
        # Get existing document
        existing = await vector_client.get_document(collection_name, document_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Merge updates
        existing_metadata = existing.get("metadata", {})
        updated_content = update.content or existing.get("content", "")
        
        if not updated_content or not updated_content.strip():
            raise HTTPException(status_code=400, detail="Content cannot be empty")
        
        # Prepare updated metadata
        if update.metadata:
            updated_metadata = {
                "name": update.metadata.name,
                "purpose": update.metadata.purpose or "",
                "tags": update.metadata.tags or "",
                **(update.metadata.custom_metadata or {})
            }
        else:
            updated_metadata = existing_metadata
        
        updated_metadata["updated_at"] = datetime.utcnow().isoformat()
        
        # Get chunking parameters
        chunk_size = update.chunk_size or existing_metadata.get("chunk_size", 1000)
        chunk_overlap = update.chunk_overlap or existing_metadata.get("chunk_overlap", 200)
        chunking_strategy = update.chunking_strategy or existing_metadata.get("chunking_strategy", "semantic")
        
        # Store and re-ingest
        db = next(get_db())
        try:
            file_content = updated_content.encode('utf-8')
            filename = f"{updated_metadata.get('name', 'document')}.txt"
            
            stored_file, collection_link, is_new = file_storage.store_file(
                file_content=file_content,
                original_filename=filename,
                collection_name=collection_name,
                document_id=document_id,
                db=db
            )
            
            db.commit()
            
            job_id = str(uuid.uuid4())
            
            await ingestion_client.trigger_ingestion(
                job_id=job_id,
                file_id=stored_file.id,
                file_path=str(file_storage.files_dir.parent / stored_file.storage_path),
                collection_name=collection_name,
                document_id=document_id,
                metadata=updated_metadata,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                chunking_strategy=chunking_strategy,
                chunk_separator=update.chunk_separator,
                max_chunks=update.max_chunks,
                version=int(existing_metadata.get("version", 1))
            )
            
        finally:
            db.close()
        
        processing_status[job_id] = {
            "task_id": job_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document update queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        return {
            "document_id": document_id,
            "task_id": job_id,
            "message": "Document update queued for processing",
            "status": ProcessingStatus.PENDING
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(collection_name: str, document_id: str):
    """Delete a document and its chunks."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.delete_document(collection_name, document_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}/chunks")
async def get_document_chunks(
    collection_name: str,
    document_id: str,
    skip: int = 0,
    limit: int = 100
):
    """Get all chunks for a specific document."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.get_document_chunks(
            collection_name=collection_name,
            document_id=document_id,
            skip=skip,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error getting document chunks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Search Endpoints
# ============================================================================

@app.post("/collections/{collection_name}/search")
async def search_documents(
    collection_name: str,
    query: str,
    n_results: int = 5
):
    """Search for similar documents in a collection."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.search(
            collection_name=collection_name,
            query=query,
            n_results=n_results
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Task/Status Endpoints
# ============================================================================

@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get processing status of a task."""
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return processing_status[task_id]


@app.get("/tasks")
async def list_tasks(status: Optional[ProcessingStatus] = None):
    """List all tasks, optionally filtered by status."""
    tasks = list(processing_status.values())
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    return {"tasks": tasks, "total": len(tasks)}


@app.post("/api/jobs/{job_id}/callback")
async def receive_job_callback(job_id: str, payload: CallbackPayload):
    """Receive status callback from ingestion service."""
    logger.info(f"Received callback for job {job_id}: {payload.status} ({payload.progress}%)")
    
    status_map = {
        "queued": ProcessingStatus.PENDING,
        "processing": ProcessingStatus.PROCESSING,
        "completed": ProcessingStatus.COMPLETED,
        "failed": ProcessingStatus.FAILED
    }
    
    mapped_status = status_map.get(payload.status.lower(), ProcessingStatus.PROCESSING)
    
    processing_status[job_id] = {
        "task_id": job_id,
        "document_id": payload.document_id or "",
        "status": mapped_status,
        "message": payload.message or "",
        "progress": payload.progress,
        "created_at": processing_status.get(job_id, {}).get("created_at", datetime.utcnow().isoformat()),
        "updated_at": payload.timestamp.isoformat() if payload.timestamp else datetime.utcnow().isoformat(),
        "chunk_count": payload.chunks_created,
        "document_type": payload.document_type,
        "error": payload.error
    }
    
    return {"status": "received", "job_id": job_id}


# ============================================================================
# Analytics Endpoints
# ============================================================================

@app.get("/analytics/stats")
async def get_stats():
    """Get overall system statistics."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.get_stats()
        return result
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/recent-activity")
async def get_recent_activity(limit: int = 10):
    """Get recent activity from task history."""
    recent_tasks = sorted(
        processing_status.values(),
        key=lambda x: x.get("updated_at", x.get("created_at", "")),
        reverse=True
    )[:limit]
    
    activities = []
    for task in recent_tasks:
        activity_type = "unknown"
        message = task.get("message", "").lower()
        if "create" in message or "upload" in message or "queue" in message:
            activity_type = "upload"
        elif "update" in message:
            activity_type = "update"
        elif "delete" in message:
            activity_type = "delete"
        
        activities.append({
            "type": activity_type,
            "message": task.get("message", ""),
            "status": task.get("status", ""),
            "timestamp": task.get("updated_at", task.get("created_at", "")),
            "collection": task.get("collection_name", "")
        })
    
    return {"activities": activities}


# ============================================================================
# Tags Endpoints
# ============================================================================

@app.get("/tags")
async def get_all_tags():
    """Get all unique tags across all collections."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.get_all_tags()
        return result
    except Exception as e:
        logger.error(f"Error getting tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/tags")
async def get_collection_tags(collection_name: str):
    """Get all unique tags in a specific collection."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.get_collection_tags(collection_name)
        return result
    except Exception as e:
        logger.error(f"Error getting collection tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Bulk Operations
# ============================================================================

@app.post("/collections/{collection_name}/documents/bulk-delete")
async def bulk_delete_documents(collection_name: str, request: BulkDeleteRequest):
    """Delete multiple documents at once."""
    get_db, ingestion_client, file_storage, vector_client, enabled = get_microservices()
    
    if not vector_client:
        raise HTTPException(status_code=503, detail="Vector service not available")
    
    try:
        result = await vector_client.bulk_delete_documents(
            collection_name=collection_name,
            document_ids=request.document_ids
        )
        return {
            "deleted": result.get("deleted_count", 0),
            "total": len(request.document_ids),
            "errors": []
        }
    except Exception as e:
        logger.error(f"Error in bulk delete: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents/bulk-update-tags")
async def bulk_update_tags(collection_name: str, request: BulkUpdateTagsRequest):
    """Update tags for multiple documents."""
    # This requires fetching and updating each document
    # For now, return not implemented
    raise HTTPException(
        status_code=501, 
        detail="Bulk tag updates not yet implemented in microservices architecture"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
