"""
Ingestion Service - Standalone microservice for document processing.
Handles file parsing, chunking, embedding generation, and ChromaDB storage.
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
import chromadb

# Add parent directory to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    get_db, init_db, ensure_directories,
    JobStatus, IngestionJob, Document, DocumentVersion, Chunk,
    BACKEND_URL, CHROMA_DB_PATH, FILES_DIR, 
    EMBEDDING_PROVIDER, EMBEDDING_MODEL,
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

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ChromaDB client
chroma_client = None
embedding_function = None


def get_embedding_function():
    """Get embedding function based on configuration."""
    from chromadb.utils import embedding_functions
    
    provider = EMBEDDING_PROVIDER
    model_name = EMBEDDING_MODEL
    
    if provider == "sentence-transformers":
        model = model_name or "sentence-transformers/all-mpnet-base-v2"
        logger.info(f"Using sentence-transformers embedding: {model}")
        return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
    elif provider == "gemini":
        model = model_name or "models/embedding-001"
        logger.info(f"Using Gemini embedding model: {model}")
        # Import Gemini embedding function
        try:
            import google.generativeai as genai
            from chromadb.utils.embedding_functions import EmbeddingFunction
            
            api_key = os.getenv("GOOGLE_API_KEY")
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            
            if credentials_path:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path, scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                genai.configure(credentials=credentials)
            elif api_key:
                genai.configure(api_key=api_key)
            else:
                raise ValueError("No Gemini credentials configured")
            
            class GeminiEmbeddingFunction(EmbeddingFunction):
                def __init__(self, model_name: str):
                    self.model_name = model_name
                
                def __call__(self, input_texts):
                    if isinstance(input_texts, str):
                        input_texts = [input_texts]
                    embeddings = []
                    for text in input_texts:
                        result = genai.embed_content(
                            model=self.model_name,
                            content=text,
                            task_type="retrieval_document"
                        )
                        if isinstance(result, dict) and 'embedding' in result:
                            embeddings.append(result['embedding'])
                        else:
                            embeddings.append(result)
                    return embeddings
            
            return GeminiEmbeddingFunction(model)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini embeddings: {e}")
            raise
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global chroma_client, embedding_function
    
    # Startup
    logger.info("Starting Ingestion Service...")
    
    # Initialize database and directories
    logger.info("Initializing database...")
    init_db()
    ensure_directories()
    logger.info("Database and directories initialized")
    
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        logger.info(f"ChromaDB connected at {CHROMA_DB_PATH}")
    except Exception as e:
        logger.error(f"Failed to connect to ChromaDB: {e}")
        raise
    
    try:
        embedding_function = get_embedding_function()
        logger.info("Embedding function initialized")
    except Exception as e:
        logger.error(f"Failed to initialize embedding function: {e}")
        raise
    
    logger.info("Ingestion Service started successfully")

    
    yield
    
    # Shutdown
    logger.info("Ingestion Service shutting down...")


# Create FastAPI app
app = FastAPI(
    title="VectorDB Ingestion Service",
    description="Microservice for document ingestion, chunking, and embedding",
    version="1.0.0",
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
    """Main ingestion processing function."""
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
        
        # Step 7: Get or create collection
        await update_job_status(job, JobStatus.PROCESSING, 50, "Connecting to vector database...", db)
        try:
            collection = chroma_client.get_collection(
                name=request.collection_name,
                embedding_function=embedding_function
            )
        except:
            collection = chroma_client.create_collection(
                name=request.collection_name,
                embedding_function=embedding_function,
                metadata={
                    "embedding_provider": EMBEDDING_PROVIDER,
                    "embedding_model": EMBEDDING_MODEL or "default",
                    "created_at": datetime.utcnow().isoformat()
                }
            )
        
        # Step 8: Store chunks
        await update_job_status(job, JobStatus.PROCESSING, 60, f"Storing {len(chunks)} chunks...", db)
        
        chunk_ids = [f"{request.document_id}_chunk_{i}" for i in range(len(chunks))]
        chunk_metadatas = []
        document_name = request.metadata.get("name", "Unknown")
        
        for i, chunk in enumerate(chunks):
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
            chunk_metadatas.append(chunk_meta)
            
            # Store chunk in database for tracking
            db_chunk = Chunk(
                id=chunk_ids[i],
                document_id=request.document_id,
                document_version=request.version,
                chunk_index=i,
                chunk_number=i + 1,
                content_hash=calculate_content_hash(chunk),
                content_length=len(chunk),
                word_count=len(chunk.split())
            )
            db.merge(db_chunk)
        
        # Add to ChromaDB
        collection.add(
            documents=chunks,
            metadatas=chunk_metadatas,
            ids=chunk_ids
        )
        
        # Step 9: Store full document
        await update_job_status(job, JobStatus.PROCESSING, 80, "Storing document...", db)
        
        full_doc_metadata = {
            **base_metadata,
            "is_chunk": False,
            "chunk_count": len(chunks),
            "content_length": len(content),
            "word_count": len(content.split()),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        collection.add(
            documents=[content],
            metadatas=[full_doc_metadata],
            ids=[request.document_id]
        )
        
        # Step 10: Update database records
        await update_job_status(job, JobStatus.PROCESSING, 90, "Updating database...", db)
        
        # Create or update Document record
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
        else:
            doc.current_version = request.version
            doc.chunk_count = len(chunks)
            doc.updated_at = datetime.utcnow()
        
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
        "version": "1.0.0"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint."""
    try:
        collections = chroma_client.list_collections()
        chromadb_status = "connected"
    except Exception as e:
        chromadb_status = f"error: {str(e)}"
    
    try:
        active_jobs = db.query(IngestionJob).filter(
            IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING])
        ).count()
        db_status = "connected"
    except Exception as e:
        active_jobs = 0
        db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy" if chromadb_status == "connected" and db_status == "connected" else "unhealthy",
        timestamp=datetime.utcnow(),
        database=db_status,
        chromadb=chromadb_status,
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
