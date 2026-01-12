"""
Ingestion Service - Standalone microservice for document processing.
Handles file parsing, chunking, and delegates vector storage to vector-service.
Communicates with backend via callbacks for status updates.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager
import uuid

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    get_db, init_db, ensure_directories,
    JobStatus, IngestionJob, Document, DocumentVersion, Chunk,
    BACKEND_URL, FILES_DIR, 
    DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNKING_STRATEGY,
    CALLBACK_TIMEOUT, CALLBACK_RETRY_ATTEMPTS, LOG_LEVEL
)

from models import (
    IngestionRequest, IngestionResponse, JobStatusResponse, 
    JobListResponse, CallbackPayload, HealthResponse
)
from ingestion_logic import (
    parse_file, chunk_text, detect_document_type, 
    prepare_metadata_for_chroma, calculate_content_hash, get_adaptive_chunk_params
)
from vector_client import VectorServiceClient

# Configuration
VECTOR_SERVICE_URL = os.getenv("VECTOR_SERVICE_URL", "http://localhost:8003")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", None)

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Vector service client
vector_client: Optional[VectorServiceClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global vector_client
    
    # Startup
    logger.info("Starting Ingestion Service...")
    
    # Initialize database and directories
    logger.info("Initializing database...")
    init_db()
    ensure_directories()
    logger.info("Database and directories initialized")
    
    # Initialize vector service client
    vector_client = VectorServiceClient(base_url=VECTOR_SERVICE_URL)
    logger.info(f"Vector service client initialized: {VECTOR_SERVICE_URL}")
    
    # Check vector service health
    health = await vector_client.health_check()
    if health.get("status") == "healthy":
        logger.info("Vector service is healthy")
    else:
        logger.warning(f"Vector service health check: {health}")
    
    logger.info("Ingestion Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Ingestion Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="VectorDB Ingestion Service",
    description="Microservice for document ingestion, chunking, and embedding",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Callback Functions
# ============================================================================

async def send_callback(job: IngestionJob, db: Session):
    """Send status callback to backend service."""
    callback_url = f"{BACKEND_URL}/api/jobs/{job.id}/callback"
    
    payload = CallbackPayload(
        job_id=job.id,
        status=JobStatus(job.status),
        progress=job.progress,
        message=job.message,
        error=job.error,
        document_id=job.document_id,
        collection_name=job.collection_name,
        chunks_created=job.chunks_created,
        timestamp=datetime.utcnow()
    )
    
    for attempt in range(CALLBACK_RETRY_ATTEMPTS):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    callback_url,
                    json=payload.model_dump(mode='json'),
                    timeout=CALLBACK_TIMEOUT
                )
                
                if response.status_code == 200:
                    job.last_callback_at = datetime.utcnow()
                    job.callback_attempts = attempt + 1
                    db.commit()
                    logger.info(f"Callback sent for job {job.id}: {job.status}")
                    return True
                else:
                    logger.warning(f"Callback failed for job {job.id}: {response.status_code}")
        except Exception as e:
            logger.warning(f"Callback attempt {attempt + 1} failed for job {job.id}: {e}")
        
        if attempt < CALLBACK_RETRY_ATTEMPTS - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    logger.error(f"All callback attempts failed for job {job.id}")
    return False


async def update_job_status(
    job: IngestionJob, 
    status: JobStatus, 
    progress: int, 
    message: str,
    db: Session,
    error: str = None
):
    """Update job status and send callback."""
    job.status = status
    job.progress = progress
    job.message = message
    job.error = error
    job.updated_at = datetime.utcnow()
    
    if status == JobStatus.PROCESSING and not job.started_at:
        job.started_at = datetime.utcnow()
    elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
        job.completed_at = datetime.utcnow()
    
    db.commit()
    
    # Send callback to backend
    await send_callback(job, db)


# ============================================================================
# Background Processing
# ============================================================================

async def process_ingestion(job_id: str, request: IngestionRequest, db: Session):
    """Main ingestion processing function - delegates storage to vector-service."""
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        logger.error(f"Job {job_id} not found")
        return
    
    try:
        # Update status to PROCESSING
        await update_job_status(job, JobStatus.PROCESSING, 5, "Starting ingestion...", db)
        
        # Step 1: Read file
        file_path = Path(request.file_path)
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")
        
        await update_job_status(job, JobStatus.PROCESSING, 10, "Reading file...", db)
        file_content = file_path.read_bytes()
        
        # Step 2: Parse file
        await update_job_status(job, JobStatus.PROCESSING, 15, "Parsing file content...", db)
        content = parse_file(file_path.name, file_content)
        
        if not content or not content.strip():
            raise ValueError("No content extracted from file")
        
        # Step 3: Detect document type
        await update_job_status(job, JobStatus.PROCESSING, 20, "Detecting document type...", db)
        document_type = request.document_type or detect_document_type(content, request.metadata)
        
        # Step 4: Get adaptive chunk parameters
        chunk_size = request.chunk_size or DEFAULT_CHUNK_SIZE
        chunk_overlap = request.chunk_overlap or DEFAULT_CHUNK_OVERLAP
        chunking_strategy = request.chunking_strategy or DEFAULT_CHUNKING_STRATEGY
        
        if chunking_strategy == "semantic":
            chunk_size, chunk_overlap = get_adaptive_chunk_params(
                document_type, chunk_size, chunk_overlap
            )
        
        # Step 5: Chunk content
        await update_job_status(job, JobStatus.PROCESSING, 30, "Chunking content...", db)
        chunks = chunk_text(
            content,
            chunk_size=chunk_size,
            overlap=chunk_overlap,
            strategy=chunking_strategy,
            separator=request.chunk_separator,
            max_chunks=request.max_chunks
        )
        
        if not chunks:
            raise ValueError("No chunks generated from content")
        
        logger.info(f"Generated {len(chunks)} chunks for job {job_id}")
        
        # Step 6: Prepare metadata
        await update_job_status(job, JobStatus.PROCESSING, 40, "Preparing metadata...", db)
        base_metadata = prepare_metadata_for_chroma(request.metadata)
        base_metadata.update({
            "document_type": document_type,
            "version": request.version,
            "is_latest": True,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunking_strategy": chunking_strategy,
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model": EMBEDDING_MODEL or "default",
        })
        
        # Step 7: Ensure collection exists via vector-service
        await update_job_status(job, JobStatus.PROCESSING, 50, "Connecting to vector service...", db)
        await vector_client.get_or_create_collection(
            name=request.collection_name,
            description=f"Collection for documents",
            metadata={
                "embedding_provider": EMBEDDING_PROVIDER,
                "embedding_model": EMBEDDING_MODEL or "default",
                "created_at": datetime.utcnow().isoformat()
            }
        )
        
        # Step 7b: Delete existing document and chunks (for updates/re-ingestion)
        await update_job_status(job, JobStatus.PROCESSING, 55, "Removing old chunks...", db)
        try:
            await vector_client.delete_document(
                collection_name=request.collection_name,
                document_id=request.document_id
            )
            logger.info(f"Deleted existing document {request.document_id} and its chunks")
        except Exception as e:
            # Document may not exist yet (first upload) - that's OK
            logger.debug(f"No existing document to delete: {e}")
        
        # Step 8: Prepare documents for vector storage
        await update_job_status(job, JobStatus.PROCESSING, 60, f"Storing {len(chunks)} chunks...", db)
        
        document_name = request.metadata.get("name", "Unknown")
        vector_documents = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{request.document_id}_chunk_{i}"
            chunk_meta = {
                **base_metadata,
                "chunk_index": i,
                "chunk_number": i + 1,
                "total_chunks": len(chunks),
                "parent_id": request.document_id,
                "parent_name": document_name,
                "is_chunk": True,
                "document_name": document_name,
                "document_version": request.version,
            }
            
            vector_documents.append({
                "id": chunk_id,
                "content": chunk,
                "metadata": chunk_meta
            })
        
        # Create Document record FIRST (before chunks due to foreign key constraint)
        doc = db.query(Document).filter(Document.id == request.document_id).first()
        if not doc:
            doc = Document(
                id=request.document_id,
                collection_name=request.collection_name,
                name=document_name,
                current_version=request.version,
                document_type=document_type,
                purpose=request.metadata.get("purpose"),
                tags=request.metadata.get("tags"),
                content_length=len(content),
                word_count=len(content.split()),
                chunk_count=len(chunks)
            )
            db.add(doc)
            db.flush()  # Flush to ensure document exists before chunks
        else:
            doc.current_version = request.version
            doc.chunk_count = len(chunks)
            doc.updated_at = datetime.utcnow()
            db.flush()
        
        # Now store chunks in local database for tracking
        for i, chunk in enumerate(chunks):
            chunk_id = f"{request.document_id}_chunk_{i}"
            db_chunk = Chunk(
                id=chunk_id,
                document_id=request.document_id,
                document_version=request.version,
                chunk_index=i,
                chunk_number=i + 1,
                content_hash=calculate_content_hash(chunk),
                content_length=len(chunk),
                word_count=len(chunk.split())
            )
            db.merge(db_chunk)
        
        # Add full document as well
        full_doc_metadata = {
            **base_metadata,
            "is_chunk": False,
            "chunk_count": len(chunks),
            "content_length": len(content),
            "word_count": len(content.split()),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        vector_documents.append({
            "id": request.document_id,
            "content": content,
            "metadata": full_doc_metadata
        })
        
        # Step 9: Store in vector-service
        await update_job_status(job, JobStatus.PROCESSING, 75, "Sending to vector database...", db)
        result = await vector_client.store_documents(
            collection_name=request.collection_name,
            documents=vector_documents,
            generate_embeddings=True
        )
        
        logger.info(f"Stored {result.get('stored_count', 0)} documents via vector-service")
        
        # Step 10: Update database records
        await update_job_status(job, JobStatus.PROCESSING, 90, "Updating database...", db)
        
        # Create DocumentVersion record
        version = DocumentVersion(
            id=str(uuid.uuid4()),
            document_id=request.document_id,
            version=request.version,
            file_id=request.file_id,
            content_hash=calculate_content_hash(content),
            content_length=len(content),
            word_count=len(content.split()),
            chunk_count=len(chunks),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            chunking_strategy=chunking_strategy
        )
        db.add(version)
        
        # Update job with results
        job.chunks_created = len(chunks)
        job.chunk_size = chunk_size
        job.chunk_overlap = chunk_overlap
        job.chunking_strategy = chunking_strategy
        
        db.commit()
        
        # Step 11: Complete!
        await update_job_status(
            job, JobStatus.COMPLETED, 100,
            f"Successfully processed {len(chunks)} chunks",
            db
        )
        
        logger.info(f"Job {job_id} completed: {len(chunks)} chunks stored")
        
    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        await update_job_status(job, JobStatus.FAILED, 0, f"Error: {str(e)}", db, error=str(e))


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "service": "VectorDB Ingestion Service",
        "status": "running",
        "version": "2.0.0",
        "vector_service": VECTOR_SERVICE_URL
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    # Check vector service
    vector_health = await vector_client.health_check()
    vector_status = "connected" if vector_health.get("status") == "healthy" else f"error: {vector_health.get('error', 'unknown')}"
    
    try:
        active_jobs = db.query(IngestionJob).filter(
            IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING])
        ).count()
        db_status = "connected"
    except Exception as e:
        active_jobs = 0
        db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy" if vector_status == "connected" and db_status == "connected" else "unhealthy",
        timestamp=datetime.utcnow(),
        database=db_status,
        chromadb=vector_status,  # Keeping field name for backwards compatibility
        active_jobs=active_jobs
    )


@app.post("/ingest", response_model=IngestionResponse)
async def ingest_document(
    request: IngestionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Queue a document for ingestion.
    Returns immediately with job ID for status tracking.
    """
    # Create job record
    job = IngestionJob(
        id=request.job_id,
        file_id=request.file_id,
        collection_name=request.collection_name,
        document_id=request.document_id,
        status=JobStatus.QUEUED,
        progress=0,
        message="Job queued for processing",
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        chunking_strategy=request.chunking_strategy
    )
    db.add(job)
    db.commit()
    
    logger.info(f"Created job {request.job_id} for document {request.document_id}")
    
    # Send initial callback
    await send_callback(job, db)
    
    # Queue background processing
    background_tasks.add_task(process_ingestion, request.job_id, request, db)
    
    return IngestionResponse(
        job_id=request.job_id,
        status=JobStatus.QUEUED,
        message="Document queued for ingestion"
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    """Get the status of an ingestion job."""
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        job_id=job.id,
        status=JobStatus(job.status),
        progress=job.progress,
        message=job.message,
        error=job.error,
        chunks_created=job.chunks_created,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at
    )


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[JobStatus] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List ingestion jobs with optional status filter."""
    query = db.query(IngestionJob)
    
    if status:
        query = query.filter(IngestionJob.status == status)
    
    total = query.count()
    jobs = query.order_by(IngestionJob.created_at.desc()).offset(skip).limit(limit).all()
    
    return JobListResponse(
        jobs=[
            JobStatusResponse(
                job_id=job.id,
                status=JobStatus(job.status),
                progress=job.progress,
                message=job.message,
                error=job.error,
                chunks_created=job.chunks_created,
                created_at=job.created_at,
                updated_at=job.updated_at,
                started_at=job.started_at,
                completed_at=job.completed_at
            )
            for job in jobs
        ],
        total=total,
        skip=skip,
        limit=limit
    )


# ============================================================================
# Document Lifecycle Endpoints (New)
# ============================================================================

@app.post("/rechunk/{document_id}")
async def rechunk_document(
    document_id: str,
    collection_name: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    chunking_strategy: str = "semantic",
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Re-chunk an existing document with new parameters.
    Deletes old chunks and creates new ones.
    """
    # Find the document
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Find the latest version's file
    latest_version = db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document_id,
        DocumentVersion.version == doc.current_version
    ).first()
    
    if not latest_version or not latest_version.file_id:
        raise HTTPException(status_code=400, detail="Cannot rechunk: original file not found")
    
    # Create a new ingestion job
    job_id = str(uuid.uuid4())
    
    # TODO: Look up the file path from file_id and create IngestionRequest
    # This requires the backend's file storage system
    
    return {
        "message": "Rechunk job created",
        "job_id": job_id,
        "document_id": document_id,
        "new_chunk_size": chunk_size,
        "new_chunking_strategy": chunking_strategy
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
