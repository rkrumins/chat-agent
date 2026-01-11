"""
Shared database models and configuration for VectorDB Manager microservices.
Uses SQLite for persistent storage of ingestion jobs, documents, versions, and chunks.
"""

import os
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Text, DateTime, 
    Boolean, ForeignKey, JSON, Index, Enum as SQLEnum, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import StaticPool
import hashlib

# Database configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "ingestion.db"))
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create engine with SQLite-specific settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False
)

# Enable foreign keys for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class JobStatus(str, Enum):
    """Ingestion job status enum"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class StoredFile(Base):
    """
    Content-addressed file storage.
    Files are stored once by SHA-256 hash and can be linked to multiple collections.
    """
    __tablename__ = "files"
    
    id = Column(String(36), primary_key=True)  # UUID
    content_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256
    original_filename = Column(String(255), nullable=False)
    file_extension = Column(String(20), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100))
    storage_path = Column(String(500), nullable=False)  # Relative path in uploads/files/
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    collection_links = relationship("FileCollectionLink", back_populates="file", cascade="all, delete-orphan")
    ingestion_jobs = relationship("IngestionJob", back_populates="file")
    
    __table_args__ = (
        Index('idx_files_hash_prefix', content_hash),
    )


class FileCollectionLink(Base):
    """
    Junction table linking files to collections.
    Enables the same file to be used in multiple collections.
    """
    __tablename__ = "file_collection_links"
    
    id = Column(String(36), primary_key=True)  # UUID
    file_id = Column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    collection_name = Column(String(255), nullable=False, index=True)
    document_id = Column(String(36), nullable=False, index=True)  # Document ID in this collection
    symlink_path = Column(String(500))  # Path to symlink in uploads/collections/
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    file = relationship("StoredFile", back_populates="collection_links")
    
    __table_args__ = (
        Index('idx_file_collection', 'file_id', 'collection_name'),
        Index('idx_collection_document', 'collection_name', 'document_id'),
    )


class IngestionJob(Base):
    """
    Tracks ingestion job status with full state history.
    Supports callback mechanism for status updates.
    """
    __tablename__ = "ingestion_jobs"
    
    id = Column(String(36), primary_key=True)  # UUID (task_id)
    file_id = Column(String(36), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    collection_name = Column(String(255), nullable=False, index=True)
    document_id = Column(String(36), nullable=False, index=True)
    
    status = Column(SQLEnum(JobStatus), default=JobStatus.QUEUED, nullable=False, index=True)
    progress = Column(Integer, default=0)  # 0-100
    message = Column(String(500))
    error = Column(Text)  # Full error message/traceback if failed
    
    # Processing metadata
    chunk_size = Column(Integer)
    chunk_overlap = Column(Integer)
    chunking_strategy = Column(String(50))
    chunks_created = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)  # When processing began
    completed_at = Column(DateTime)  # When processing finished (success or failure)
    
    # Callback tracking
    last_callback_at = Column(DateTime)
    callback_attempts = Column(Integer, default=0)
    
    # Relationships
    file = relationship("StoredFile", back_populates="ingestion_jobs")
    
    __table_args__ = (
        Index('idx_job_status_created', 'status', 'created_at'),
    )


class Document(Base):
    """
    Document metadata and current version tracking.
    """
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True)  # UUID
    collection_name = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)  # User-provided document name
    
    current_version = Column(Integer, default=1, nullable=False)
    is_latest = Column(Boolean, default=True, nullable=False)
    
    # Document type and metadata
    document_type = Column(String(50))  # book, definition, article, etc.
    purpose = Column(Text)
    tags = Column(String(500))  # Comma-separated
    custom_metadata = Column(JSON)
    
    # Content stats
    content_length = Column(Integer)
    word_count = Column(Integer)
    chunk_count = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_doc_collection_name', 'collection_name', 'name'),
    )


class DocumentVersion(Base):
    """
    Document version history with diff tracking.
    """
    __tablename__ = "document_versions"
    
    id = Column(String(36), primary_key=True)  # UUID
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    
    file_id = Column(String(36), ForeignKey("files.id", ondelete="SET NULL"))  # Source file for this version
    content_hash = Column(String(64))  # Hash of the processed content
    
    # Change tracking
    change_notes = Column(Text)
    changed_by = Column(String(100))  # User or system identifier
    
    # Stats at this version
    content_length = Column(Integer)
    word_count = Column(Integer)
    chunk_count = Column(Integer)
    
    # Processing params used
    chunk_size = Column(Integer)
    chunk_overlap = Column(Integer)
    chunking_strategy = Column(String(50))
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="versions")
    
    __table_args__ = (
        Index('idx_version_doc_version', 'document_id', 'version'),
    )


class Chunk(Base):
    """
    Individual chunk metadata and tracking.
    Actual chunk content is stored in ChromaDB, this tracks metadata and history.
    """
    __tablename__ = "chunks"
    
    id = Column(String(36), primary_key=True)  # UUID (matches ChromaDB ID)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    document_version = Column(Integer, nullable=False)
    
    chunk_index = Column(Integer, nullable=False)  # 0-based index in document
    chunk_number = Column(Integer, nullable=False)  # 1-based for display
    
    # Content hash for change detection
    content_hash = Column(String(64), nullable=False)
    
    # Chunk metadata
    content_length = Column(Integer)
    word_count = Column(Integer)
    content_type = Column(String(50))  # paragraph, list, code, table, etc.
    section_title = Column(String(255))
    
    # Position info
    start_char = Column(Integer)
    end_char = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    __table_args__ = (
        Index('idx_chunk_doc_version', 'document_id', 'document_version'),
        Index('idx_chunk_content_hash', 'content_hash'),
    )


def init_db():
    """Initialize the database, creating all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Get a database session. Use as context manager or dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def calculate_content_hash(content: bytes) -> str:
    """Calculate SHA-256 hash of content."""
    return hashlib.sha256(content).hexdigest()


# Note: Call init_db() explicitly at service startup, not during import
# init_db()
