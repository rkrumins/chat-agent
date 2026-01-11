"""
Configuration module for VectorDB Manager microservices.
"""

from .database import (
    Base, engine, SessionLocal, get_db, init_db,
    JobStatus, StoredFile, FileCollectionLink, IngestionJob,
    Document, DocumentVersion, Chunk,
    calculate_content_hash
)
from .settings import (
    PROJECT_ROOT, UPLOADS_ROOT, FILES_DIR, COLLECTIONS_DIR,
    DATABASE_PATH, DATABASE_URL, CHROMA_DB_PATH,
    BACKEND_URL, INGESTION_URL,
    BACKEND_HOST, BACKEND_PORT, INGESTION_HOST, INGESTION_PORT,
    EMBEDDING_PROVIDER, EMBEDDING_MODEL,
    DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNKING_STRATEGY,
    MAX_FILE_SIZE, CALLBACK_TIMEOUT, CALLBACK_RETRY_ATTEMPTS, LOG_LEVEL,
    ensure_directories
)

__all__ = [
    # Database
    'Base', 'engine', 'SessionLocal', 'get_db', 'init_db',
    'JobStatus', 'StoredFile', 'FileCollectionLink', 'IngestionJob',
    'Document', 'DocumentVersion', 'Chunk', 'calculate_content_hash',
    # Settings
    'PROJECT_ROOT', 'UPLOADS_ROOT', 'FILES_DIR', 'COLLECTIONS_DIR',
    'DATABASE_PATH', 'DATABASE_URL', 'CHROMA_DB_PATH',
    'BACKEND_URL', 'INGESTION_URL',
    'BACKEND_HOST', 'BACKEND_PORT', 'INGESTION_HOST', 'INGESTION_PORT',
    'EMBEDDING_PROVIDER', 'EMBEDDING_MODEL',
    'DEFAULT_CHUNK_SIZE', 'DEFAULT_CHUNK_OVERLAP', 'DEFAULT_CHUNKING_STRATEGY',
    'MAX_FILE_SIZE', 'CALLBACK_TIMEOUT', 'CALLBACK_RETRY_ATTEMPTS', 'LOG_LEVEL',
    'ensure_directories'
]

