"""
Ingestion Client for backend service.
Handles communication with the ingestion microservice via REST API.
"""

import os
import hashlib
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING
import uuid

import httpx

# Add parent directory to import config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Lazy import to avoid blocking at module load time
# Config module creates SQLAlchemy engine which can conflict with uvicorn's async handling
_config_loaded = False
_INGESTION_URL = None
_FILES_DIR = None
_COLLECTIONS_DIR = None
_StoredFile = None
_FileCollectionLink = None


def _load_config():
    """Lazy load config module."""
    global _config_loaded, _INGESTION_URL, _FILES_DIR, _COLLECTIONS_DIR, _StoredFile, _FileCollectionLink
    if not _config_loaded:
        from config import INGESTION_URL, FILES_DIR, COLLECTIONS_DIR, StoredFile, FileCollectionLink
        _INGESTION_URL = INGESTION_URL
        _FILES_DIR = FILES_DIR
        _COLLECTIONS_DIR = COLLECTIONS_DIR
        _StoredFile = StoredFile
        _FileCollectionLink = FileCollectionLink
        _config_loaded = True


logger = logging.getLogger(__name__)




class IngestionClient:
    """Client for communicating with the ingestion microservice."""
    
    def __init__(self, base_url: str = None):
        _load_config()  # Ensure config is loaded
        self.base_url = base_url or _INGESTION_URL
        self.timeout = 30.0

    
    async def trigger_ingestion(
        self,
        job_id: str,
        file_id: str,
        file_path: str,
        collection_name: str,
        document_id: str,
        metadata: Dict[str, Any],
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        chunking_strategy: str = "semantic",
        chunk_separator: Optional[str] = None,
        max_chunks: Optional[int] = None,
        document_type: Optional[str] = None,
        version: int = 1,
        create_new_version: bool = False
    ) -> Dict[str, Any]:
        """
        Trigger ingestion of a document by calling the ingestion service.
        Returns immediately with job status.
        """
        payload = {
            "job_id": job_id,
            "file_id": file_id,
            "file_path": file_path,
            "collection_name": collection_name,
            "document_id": document_id,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunking_strategy": chunking_strategy,
            "chunk_separator": chunk_separator,
            "max_chunks": max_chunks,
            "metadata": metadata,
            "document_type": document_type,
            "version": version,
            "create_new_version": create_new_version
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/ingest",
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"Ingestion trigger failed: {response.status_code} - {response.text}")
                    raise Exception(f"Ingestion service returned {response.status_code}: {response.text}")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to ingestion service: {e}")
            raise Exception(f"Failed to connect to ingestion service at {self.base_url}: {e}")
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of an ingestion job from the ingestion service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/jobs/{job_id}",
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 404:
                    return None
                else:
                    raise Exception(f"Failed to get job status: {response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Failed to get job status: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of ingestion service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/health",
                    timeout=5.0
                )
                return response.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}


class FileStorageManager:
    """
    Manages content-addressed file storage.
    Files are stored by SHA-256 hash for deduplication.
    """
    
    def __init__(self):
        _load_config()  # Ensure config is loaded
        self.files_dir = _FILES_DIR
        self.collections_dir = _COLLECTIONS_DIR
        self._initialized = False
    
    def _ensure_dirs(self):
        """Create directories on first use."""
        if not self._initialized:
            self.files_dir.mkdir(parents=True, exist_ok=True)
            self.collections_dir.mkdir(parents=True, exist_ok=True)
            self._initialized = True

    
    def store_file(
        self,
        file_content: bytes,
        original_filename: str,
        collection_name: str,
        document_id: str,
        db
    ):
        """
        Store a file using content-addressed storage.
        
        Returns:
            (StoredFile, FileCollectionLink, is_new_file)
            is_new_file is True if this is new content, False if duplicate
        """
        self._ensure_dirs()
        
        # Calculate content hash
        content_hash = hashlib.sha256(file_content).hexdigest()
        
        # Get file extension
        file_ext = Path(original_filename).suffix.lower()
        
        # Check if file already exists
        existing_file = db.query(_StoredFile).filter(
            _StoredFile.content_hash == content_hash
        ).first()
        
        is_new_file = existing_file is None
        
        if is_new_file:
            # Store the file
            file_id = str(uuid.uuid4())
            hash_prefix = content_hash[:2]
            
            # Create prefix directory
            prefix_dir = self.files_dir / hash_prefix
            prefix_dir.mkdir(exist_ok=True)
            
            # Store file
            storage_filename = f"{content_hash}{file_ext}"
            storage_path = prefix_dir / storage_filename
            storage_path.write_bytes(file_content)
            
            # Create database record
            stored_file = _StoredFile(
                id=file_id,
                content_hash=content_hash,
                original_filename=original_filename,
                file_extension=file_ext,
                file_size=len(file_content),
                storage_path=str(storage_path.relative_to(self.files_dir.parent))
            )
            db.add(stored_file)
            
            logger.info(f"Stored new file: {original_filename} -> {storage_path}")
        else:
            stored_file = existing_file
            logger.info(f"File already exists with hash {content_hash[:16]}...")
        
        # Create collection link
        collection_dir = self.collections_dir / collection_name
        collection_dir.mkdir(exist_ok=True)
        
        symlink_filename = f"{document_id}{file_ext}"
        symlink_path = collection_dir / symlink_filename
        
        # Create symlink (or copy if symlinks not supported)
        actual_file_path = self.files_dir.parent / stored_file.storage_path
        
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        
        try:
            symlink_path.symlink_to(actual_file_path)
        except OSError:
            # Symlinks not supported, create a copy
            shutil.copy2(actual_file_path, symlink_path)
        
        # Create collection link record
        link_id = str(uuid.uuid4())
        collection_link = _FileCollectionLink(
            id=link_id,
            file_id=stored_file.id,
            collection_name=collection_name,
            document_id=document_id,
            symlink_path=str(symlink_path.relative_to(self.collections_dir.parent))
        )
        db.add(collection_link)
        
        db.commit()
        
        return stored_file, collection_link, is_new_file
    
    def get_file_path(self, stored_file) -> Path:
        """Get the absolute path to a stored file."""
        return self.files_dir.parent / stored_file.storage_path


# Note: Do NOT instantiate global instances here
# The main.py uses get_microservices() which instantiates on first use
