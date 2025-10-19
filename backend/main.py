from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import uuid
from datetime import datetime
import asyncio
from enum import Enum
import logging
import json
import io
from pathlib import Path

# File parsing imports
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="VectorDB Management API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ChromaDB client
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Initialize embedding function (MUST match chatbot's embedding model!)
# Using sentence-transformers model that chatbot uses
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# In-memory storage for processing status
processing_status: Dict[str, Dict[str, Any]] = {}


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentMetadata(BaseModel):
    name: str
    purpose: Optional[str] = ""
    tags: Optional[str] = ""  # Changed to string (comma-separated)
    custom_metadata: Optional[Dict[str, Any]] = {}


class DocumentCreate(BaseModel):
    collection_name: str
    metadata: DocumentMetadata
    content: Optional[str] = ""
    chunk_size: Optional[int] = 500
    chunk_overlap: Optional[int] = 50
    create_new_version: Optional[bool] = False  # If True, create new version of existing doc


class DocumentUpdate(BaseModel):
    metadata: Optional[DocumentMetadata] = None
    content: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None


class VersionInfo(BaseModel):
    version: int
    document_id: str
    created_at: str
    updated_by: Optional[str] = None
    change_notes: Optional[str] = None


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    metadata: Optional[Dict[str, Any]] = {}


class DocumentResponse(BaseModel):
    id: str
    collection_name: str
    metadata: Dict[str, Any]
    content: str
    created_at: str
    updated_at: str


class ProcessingStatusResponse(BaseModel):
    task_id: str
    status: ProcessingStatus
    message: str
    progress: int
    created_at: str
    updated_at: str


# File parsing functions
def parse_pdf(file_content: bytes) -> str:
    """Extract text from PDF file"""
    if PdfReader is None:
        raise HTTPException(status_code=500, detail="PDF parsing not available. Install PyPDF2.")
    
    try:
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing PDF: {str(e)}")


def parse_docx(file_content: bytes) -> str:
    """Extract text from Word document"""
    if DocxDocument is None:
        raise HTTPException(status_code=500, detail="DOCX parsing not available. Install python-docx.")
    
    try:
        docx_file = io.BytesIO(file_content)
        doc = DocxDocument(docx_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing DOCX: {str(e)}")


def parse_txt(file_content: bytes) -> str:
    """Extract text from TXT file"""
    try:
        return file_content.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return file_content.decode('latin-1')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error parsing TXT: {str(e)}")


def parse_json(file_content: bytes) -> str:
    """Extract text from JSON file"""
    try:
        data = json.loads(file_content.decode('utf-8'))
        # Convert JSON to readable text format
        return json.dumps(data, indent=2)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error parsing JSON: {str(e)}")


def parse_file(filename: str, file_content: bytes) -> str:
    """Parse file based on extension"""
    extension = Path(filename).suffix.lower()
    
    parsers = {
        '.pdf': parse_pdf,
        '.docx': parse_docx,
        '.doc': parse_docx,
        '.txt': parse_txt,
        '.text': parse_txt,
        '.json': parse_json,
    }
    
    parser = parsers.get(extension)
    if parser is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}. Supported: PDF, DOCX, TXT, JSON"
        )
    
    return parser(file_content)


# Helper functions
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks"""
    chunks = []
    start = 0
    text_length = len(text)
    
    if text_length == 0:
        return []
    
    while start < text_length:
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():  # Only add non-empty chunks
            chunks.append(chunk)
        start = end - overlap
    
    return chunks if chunks else [text]  # Return full text if no chunks


def prepare_metadata_for_chroma(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare metadata for ChromaDB - convert lists to strings"""
    chroma_metadata = {}
    for key, value in metadata.items():
        if isinstance(value, list):
            # Convert list to comma-separated string
            chroma_metadata[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            # Convert dict to JSON string
            chroma_metadata[key] = json.dumps(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            chroma_metadata[key] = value
        else:
            # Convert other types to string
            chroma_metadata[key] = str(value)
    return chroma_metadata


def get_next_version_number(collection, document_name: str) -> int:
    """Get the next version number for a document name"""
    try:
        all_docs = collection.get(include=["metadatas"])
        max_version = 0
        
        for i, doc_id in enumerate(all_docs["ids"]):
            doc_metadata = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
            if (doc_metadata.get("name") == document_name and 
                doc_metadata.get("is_chunk") is False):
                version = doc_metadata.get("version", 1)
                max_version = max(max_version, version)
        
        return max_version + 1
    except:
        return 1


def mark_previous_versions_as_old(collection, document_name: str):
    """Mark all previous versions of a document as not latest"""
    try:
        all_docs = collection.get(include=["metadatas"])
        
        for i, doc_id in enumerate(all_docs["ids"]):
            doc_metadata = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
            if (doc_metadata.get("name") == document_name and 
                doc_metadata.get("is_chunk") is False and
                doc_metadata.get("is_latest") is True):
                # Update metadata to mark as not latest
                doc_metadata["is_latest"] = False
                # Note: ChromaDB doesn't support in-place metadata updates easily
                # This is a limitation we'll document
                logger.info(f"Document {doc_id} is now an old version")
    except Exception as e:
        logger.warning(f"Error marking old versions: {str(e)}")


async def process_document_async(
    task_id: str,
    collection_name: str,
    document_id: str,
    content: str,
    metadata: Dict[str, Any],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    version: int = 1
):
    """Process document asynchronously with status updates"""
    try:
        processing_status[task_id]["status"] = ProcessingStatus.PROCESSING
        processing_status[task_id]["message"] = "Chunking document..."
        processing_status[task_id]["progress"] = 20
        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
        # Simulate chunking
        await asyncio.sleep(0.5)
        chunks = chunk_text(content, chunk_size, chunk_overlap)
        
        processing_status[task_id]["message"] = f"Processing {len(chunks)} chunks..."
        processing_status[task_id]["progress"] = 50
        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
        # Get or create collection with embedding function
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"description": metadata.get("description", "")},
            embedding_function=embedding_function
        )
        
        # Simulate embedding generation
        await asyncio.sleep(0.5)
        
        processing_status[task_id]["message"] = "Storing in vector database..."
        processing_status[task_id]["progress"] = 80
        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
        # Prepare metadata for ChromaDB (convert lists to strings)
        chroma_metadata = prepare_metadata_for_chroma(metadata)
        chroma_metadata["chunk_size"] = chunk_size
        chroma_metadata["chunk_overlap"] = chunk_overlap
        chroma_metadata["version"] = version
        chroma_metadata["is_latest"] = True
        
        # Store chunks
        if len(chunks) > 1:
            chunk_ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
            chunk_metadata = [{
                **chroma_metadata,
                "chunk_index": i,
                "parent_id": document_id,
                "is_chunk": True
            } for i in range(len(chunks))]
            
            # Add chunks to collection
            collection.add(
                documents=chunks,
                metadatas=chunk_metadata,
                ids=chunk_ids
            )
        
        # Store full document metadata
        full_doc_metadata = {
            **chroma_metadata,
            "is_chunk": False,
            "chunk_count": len(chunks),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        collection.add(
            documents=[content],
            metadatas=[full_doc_metadata],
            ids=[document_id]
        )
        
        processing_status[task_id]["status"] = ProcessingStatus.COMPLETED
        processing_status[task_id]["message"] = "Document processed successfully"
        processing_status[task_id]["progress"] = 100
        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Document {document_id} processed successfully")
        
    except Exception as e:
        logger.error(f"Error processing document {document_id}: {str(e)}")
        processing_status[task_id]["status"] = ProcessingStatus.FAILED
        processing_status[task_id]["message"] = f"Error: {str(e)}"
        processing_status[task_id]["updated_at"] = datetime.utcnow().isoformat()


# API Endpoints

@app.get("/")
async def root():
    return {
        "message": "VectorDB Management API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# Collection endpoints

@app.get("/collections")
async def list_collections():
    """List all collections"""
    try:
        collections = chroma_client.list_collections()
        result_collections = []
        
        for col in collections:
            # Get only non-chunk documents for accurate count
            try:
                all_docs = col.get(include=["metadatas"])
                doc_count = sum(1 for i, _ in enumerate(all_docs["ids"]) 
                              if all_docs["metadatas"][i].get("is_chunk") is False)
            except:
                doc_count = col.count()  # Fallback to total count
            
            result_collections.append({
                "name": col.name,
                "id": col.id,
                "metadata": col.metadata,
                "count": doc_count
            })
        
        return {"collections": result_collections}
    except Exception as e:
        logger.error(f"Error listing collections: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections")
async def create_collection(collection: CollectionCreate):
    """Create a new collection"""
    try:
        col = chroma_client.create_collection(
            name=collection.name,
            metadata={
                "description": collection.description,
                **collection.metadata,
                "created_at": datetime.utcnow().isoformat()
            },
            embedding_function=embedding_function
        )
        return {
            "name": col.name,
            "id": col.id,
            "metadata": col.metadata,
            "message": "Collection created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating collection: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete a collection"""
    try:
        chroma_client.delete_collection(name=collection_name)
        return {"message": f"Collection '{collection_name}' deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting collection: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))


# Document endpoints

@app.get("/collections/{collection_name}/documents")
async def list_documents(
    collection_name: str, 
    skip: int = 0, 
    limit: int = 100,
    show_all_versions: bool = False
):
    """List all documents in a collection (latest versions by default)"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get all non-chunk documents
        all_results = collection.get(include=["documents", "metadatas"])
        
        documents = []
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Skip chunks
            if metadata.get("is_chunk") is True:
                continue
            
            # Skip old versions unless requested
            if not show_all_versions and metadata.get("is_latest") is False:
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
        paginated_docs = documents[skip:skip+limit]
        
        return {
            "documents": paginated_docs,
            "total": len(documents),
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/collections/{collection_name}/documents/{document_id}")
async def get_document(collection_name: str, document_id: str):
    """Get a specific document"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        result = collection.get(
            ids=[document_id],
            include=["documents", "metadatas"]
        )
        
        if not result["ids"]:
            raise HTTPException(status_code=404, detail="Document not found")
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents")
async def create_document(
    collection_name: str,
    document: DocumentCreate,
    background_tasks: BackgroundTasks
):
    """Create a new document from text"""
    try:
        if not document.content and not document.content.strip():
            raise HTTPException(status_code=400, detail="Content is required")
        
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Check if creating a new version
        version = 1
        if document.create_new_version:
            version = get_next_version_number(collection, document.metadata.name)
            mark_previous_versions_as_old(collection, document.metadata.name)
        
        document_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Initialize processing status
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Prepare metadata
        metadata = {
            "name": document.metadata.name,
            "purpose": document.metadata.purpose or "",
            "tags": document.metadata.tags or "",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **document.metadata.custom_metadata
        }
        
        # Queue background processing
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            document.content,
            metadata,
            document.chunk_size,
            document.chunk_overlap,
            version
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": version,
            "message": f"Document queued for processing (version {version})",
            "status": ProcessingStatus.PENDING
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_name}/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    collection_name: str,
    file: UploadFile = File(...),
    name: str = Form(...),
    purpose: str = Form(""),
    tags: str = Form(""),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    custom_metadata: str = Form("{}"),
    create_new_version: bool = Form(False)
):
    """Upload and process a document file"""
    try:
        # Read file content
        file_content = await file.read()
        
        # Parse file based on type
        content = parse_file(file.filename, file_content)
        
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="File appears to be empty or unreadable")
        
        collection = chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Check if creating a new version
        version = 1
        if create_new_version:
            version = get_next_version_number(collection, name)
            mark_previous_versions_as_old(collection, name)
        
        document_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        
        # Initialize processing status
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
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
            "filename": file.filename,
            "file_type": Path(file.filename).suffix.lower(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            **custom_meta
        }
        
        # Queue background processing
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            content,
            metadata,
            chunk_size,
            chunk_overlap,
            version
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "version": version,
            "message": f"Document queued for processing (version {version})",
            "status": ProcessingStatus.PENDING,
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/collections/{collection_name}/documents/{document_id}")
async def update_document(
    collection_name: str,
    document_id: str,
    update: DocumentUpdate,
    background_tasks: BackgroundTasks
):
    """Update an existing document"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Get existing document
        existing = collection.get(
            ids=[document_id],
            include=["documents", "metadatas"]
        )
        
        if not existing["ids"]:
            raise HTTPException(status_code=404, detail="Document not found")
        
        existing_metadata = existing["metadatas"][0]
        existing_content = existing["documents"][0]
        
        # Prepare updated metadata
        updated_metadata = existing_metadata.copy()
        
        if update.metadata:
            updated_metadata.update({
                "name": update.metadata.name,
                "purpose": update.metadata.purpose or "",
                "tags": update.metadata.tags or "",
                **update.metadata.custom_metadata
            })
        
        updated_metadata["updated_at"] = datetime.utcnow().isoformat()
        
        # Use updated content or keep existing
        updated_content = update.content if update.content else existing_content
        
        # Get chunk parameters
        chunk_size = update.chunk_size if update.chunk_size else existing_metadata.get("chunk_size", 500)
        chunk_overlap = update.chunk_overlap if update.chunk_overlap else existing_metadata.get("chunk_overlap", 50)
        
        # Delete old chunks
        try:
            # Get all documents to find chunks manually
            all_results = collection.get(include=["metadatas"])
            chunk_ids_to_delete = []
            
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                if metadata.get("parent_id") == document_id and metadata.get("is_chunk") is True:
                    chunk_ids_to_delete.append(doc_id)
            
            if chunk_ids_to_delete:
                collection.delete(ids=chunk_ids_to_delete)
                logger.info(f"Deleted {len(chunk_ids_to_delete)} old chunks")
        except Exception as e:
            logger.warning(f"Error deleting old chunks: {str(e)}, continuing with update")
        
        # Delete old document
        collection.delete(ids=[document_id])
        
        # Create new task for processing
        task_id = str(uuid.uuid4())
        processing_status[task_id] = {
            "task_id": task_id,
            "document_id": document_id,
            "status": ProcessingStatus.PENDING,
            "message": "Document update queued for processing",
            "progress": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Queue background processing
        background_tasks.add_task(
            process_document_async,
            task_id,
            collection_name,
            document_id,
            updated_content,
            updated_metadata,
            chunk_size,
            chunk_overlap
        )
        
        return {
            "document_id": document_id,
            "task_id": task_id,
            "message": "Document update queued for processing",
            "status": ProcessingStatus.PENDING
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(collection_name: str, document_id: str):
    """Delete a document and its chunks"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        # Try to delete document chunks if they exist
        try:
            # Get all documents in collection to find chunks manually
            all_results = collection.get(include=["metadatas"])
            chunk_ids_to_delete = []
            
            for i, doc_id in enumerate(all_results["ids"]):
                metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
                # Check if this is a chunk of our document
                if metadata.get("parent_id") == document_id and metadata.get("is_chunk") is True:
                    chunk_ids_to_delete.append(doc_id)
            
            if chunk_ids_to_delete:
                collection.delete(ids=chunk_ids_to_delete)
                logger.info(f"Deleted {len(chunk_ids_to_delete)} chunks for document {document_id}")
        except Exception as chunk_error:
            logger.warning(f"Error deleting chunks: {str(chunk_error)}, continuing with document deletion")
        
        # Delete main document
        try:
            collection.delete(ids=[document_id])
            logger.info(f"Deleted document {document_id}")
        except Exception as doc_error:
            logger.error(f"Error deleting main document: {str(doc_error)}")
            raise HTTPException(status_code=404, detail=f"Document not found or already deleted: {str(doc_error)}")
        
        return {"message": f"Document '{document_id}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Document version endpoints

@app.get("/collections/{collection_name}/documents/by-name/{document_name}/versions")
async def list_document_versions(collection_name: str, document_name: str):
    """Get all versions of a document by name"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        all_results = collection.get(include=["documents", "metadatas"])
        
        versions = []
        for i, doc_id in enumerate(all_results["ids"]):
            metadata = all_results["metadatas"][i] if all_results["metadatas"] else {}
            
            # Only include documents with matching name (not chunks)
            if metadata.get("name") == document_name and metadata.get("is_chunk") is False:
                versions.append({
                    "id": doc_id,
                    "version": metadata.get("version", 1),
                    "is_latest": metadata.get("is_latest", False),
                    "created_at": metadata.get("created_at", ""),
                    "updated_at": metadata.get("updated_at", ""),
                    "purpose": metadata.get("purpose", ""),
                    "tags": metadata.get("tags", ""),
                    "chunk_count": metadata.get("chunk_count", 1)
                })
        
        # Sort by version descending
        versions.sort(key=lambda x: x["version"], reverse=True)
        
        return {
            "document_name": document_name,
            "versions": versions,
            "total_versions": len(versions)
        }
    except Exception as e:
        logger.error(f"Error listing document versions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Processing status endpoints

@app.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get processing status of a task"""
    if task_id not in processing_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return processing_status[task_id]


@app.get("/tasks")
async def list_tasks(status: Optional[ProcessingStatus] = None):
    """List all tasks, optionally filtered by status"""
    tasks = list(processing_status.values())
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    return {"tasks": tasks, "total": len(tasks)}


# Search endpoint

@app.post("/collections/{collection_name}/search")
async def search_documents(
    collection_name: str,
    query: str,
    n_results: int = 5
):
    """Search for similar documents in a collection"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )
        
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                search_results.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0
                })
        
        return {
            "query": query,
            "results": search_results,
            "count": len(search_results)
        }
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Analytics endpoints

@app.get("/analytics/stats")
async def get_stats():
    """Get overall system statistics"""
    try:
        collections = chroma_client.list_collections()
        
        total_collections = len(collections)
        total_documents = 0
        total_chunks = 0
        collection_details = []
        
        for collection in collections:
            col = chroma_client.get_collection(
                name=collection.name,
                embedding_function=embedding_function
            )
            all_items = col.get(include=["metadatas"])
            
            # Count actual documents (not chunks)
            documents = [item for item in all_items['metadatas'] if not item.get('is_chunk', False)]
            chunks = [item for item in all_items['metadatas'] if item.get('is_chunk', False)]
            
            doc_count = len(documents)
            chunk_count = len(chunks)
            
            total_documents += doc_count
            total_chunks += chunk_count
            
            collection_details.append({
                "name": collection.name,
                "document_count": doc_count,
                "chunk_count": chunk_count,
                "metadata": collection.metadata or {}
            })
        
        return {
            "total_collections": total_collections,
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "collections": collection_details
        }
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/recent-activity")
async def get_recent_activity(limit: int = 10):
    """Get recent activity (from task history)"""
    try:
        # Get recent completed tasks
        recent_tasks = sorted(
            processing_status.values(),
            key=lambda x: x.get("updated_at", x.get("created_at", "")),
            reverse=True
        )[:limit]
        
        activities = []
        for task in recent_tasks:
            activity_type = "unknown"
            if "create" in task.get("message", "").lower() or "upload" in task.get("message", "").lower():
                activity_type = "upload"
            elif "update" in task.get("message", "").lower():
                activity_type = "update"
            elif "delete" in task.get("message", "").lower():
                activity_type = "delete"
            
            activities.append({
                "type": activity_type,
                "message": task.get("message", ""),
                "status": task.get("status", ""),
                "timestamp": task.get("updated_at", task.get("created_at", "")),
                "collection": task.get("collection_name", "")
            })
        
        return {"activities": activities}
    except Exception as e:
        logger.error(f"Error getting recent activity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Tag management endpoints

@app.get("/tags")
async def get_all_tags():
    """Get all unique tags across all collections"""
    try:
        collections = chroma_client.list_collections()
        tag_counts = {}
        
        for collection in collections:
            col = chroma_client.get_collection(
                name=collection.name,
                embedding_function=embedding_function
            )
            all_items = col.get(include=["metadatas"])
            
            for metadata in all_items['metadatas']:
                if metadata.get('is_chunk', False):
                    continue
                    
                tags_str = metadata.get('tags', '')
                if tags_str:
                    tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                    for tag in tags:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        # Sort by count (most popular first)
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
            "total": len(sorted_tags)
        }
    except Exception as e:
        logger.error(f"Error getting tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_name}/tags")
async def get_collection_tags(collection_name: str):
    """Get all unique tags in a specific collection"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        all_items = collection.get(include=["metadatas"])
        
        tag_counts = {}
        for metadata in all_items['metadatas']:
            if metadata.get('is_chunk', False):
                continue
                
            tags_str = metadata.get('tags', '')
            if tags_str:
                tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                for tag in tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "collection": collection_name,
            "tags": [{"tag": tag, "count": count} for tag, count in sorted_tags],
            "total": len(sorted_tags)
        }
    except Exception as e:
        logger.error(f"Error getting collection tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Bulk operations endpoints

class BulkDeleteRequest(BaseModel):
    document_ids: List[str]


@app.post("/collections/{collection_name}/documents/bulk-delete")
async def bulk_delete_documents(
    collection_name: str,
    request: BulkDeleteRequest
):
    """Delete multiple documents at once"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        deleted_count = 0
        errors = []
        
        for doc_id in request.document_ids:
            try:
                # Get all items to find chunks
                all_items = collection.get(include=["metadatas"])
                
                # Find chunks for this document
                chunk_ids = []
                for i, metadata in enumerate(all_items['metadatas']):
                    if metadata.get('parent_id') == doc_id and metadata.get('is_chunk', False):
                        chunk_ids.append(all_items['ids'][i])
                
                # Delete chunks
                if chunk_ids:
                    collection.delete(ids=chunk_ids)
                
                # Delete main document
                collection.delete(ids=[doc_id])
                deleted_count += 1
                
            except Exception as e:
                errors.append({"document_id": doc_id, "error": str(e)})
        
        return {
            "deleted": deleted_count,
            "total": len(request.document_ids),
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkUpdateTagsRequest(BaseModel):
    document_ids: List[str]
    tags: str
    mode: str = "replace"  # "replace", "append", or "remove"


@app.post("/collections/{collection_name}/documents/bulk-update-tags")
async def bulk_update_tags(
    collection_name: str,
    request: BulkUpdateTagsRequest
):
    """Update tags for multiple documents"""
    try:
        collection = chroma_client.get_collection(
            name=collection_name,
            embedding_function=embedding_function
        )
        
        updated_count = 0
        errors = []
        
        for doc_id in request.document_ids:
            try:
                # Get current document
                result = collection.get(ids=[doc_id], include=["metadatas"])
                if not result['ids']:
                    errors.append({"document_id": doc_id, "error": "Document not found"})
                    continue
                
                current_metadata = result['metadatas'][0]
                current_tags = current_metadata.get('tags', '')
                
                # Update tags based on mode
                if request.mode == "replace":
                    new_tags = request.tags
                elif request.mode == "append":
                    existing = set([t.strip() for t in current_tags.split(',') if t.strip()])
                    new = set([t.strip() for t in request.tags.split(',') if t.strip()])
                    new_tags = ', '.join(sorted(existing.union(new)))
                elif request.mode == "remove":
                    existing = set([t.strip() for t in current_tags.split(',') if t.strip()])
                    to_remove = set([t.strip() for t in request.tags.split(',') if t.strip()])
                    new_tags = ', '.join(sorted(existing - to_remove))
                else:
                    new_tags = request.tags
                
                # Update metadata
                current_metadata['tags'] = new_tags
                collection.update(
                    ids=[doc_id],
                    metadatas=[current_metadata]
                )
                
                updated_count += 1
                
            except Exception as e:
                errors.append({"document_id": doc_id, "error": str(e)})
        
        return {
            "updated": updated_count,
            "total": len(request.document_ids),
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Error in bulk update tags: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
