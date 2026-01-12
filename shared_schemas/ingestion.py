"""
Ingestion-related Pydantic models.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from .base import JobStatus, ChunkingStrategy


class ConnectorType(str, Enum):
    """Types of data connectors."""
    FILE_UPLOAD = "file_upload"
    TEXT_INPUT = "text_input"
    WEB_CRAWLER = "web_crawler"      # Future
    CONFLUENCE = "confluence"         # Future
    SHAREPOINT = "sharepoint"         # Future
    DATABASE = "database"             # Future
    API = "api"                       # Future


class IngestionRequest(BaseModel):
    """Request to ingest a document."""
    job_id: str = Field(..., description="Unique job identifier (UUID)")
    file_id: str = Field(..., description="File ID in the storage database")
    file_path: str = Field(..., description="Absolute path to the file to ingest")
    collection_name: str = Field(..., description="Target collection name")
    document_id: str = Field(..., description="Document ID for this collection")
    
    # Processing parameters
    chunk_size: int = Field(default=1000, ge=100, le=10000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    chunking_strategy: str = Field(default="semantic")
    chunk_separator: Optional[str] = Field(default=None)
    max_chunks: Optional[int] = Field(default=None, ge=1)
    
    # Document metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    document_type: Optional[str] = Field(default=None)
    version: int = Field(default=1, ge=1)
    create_new_version: bool = Field(default=False)
    
    # Callback configuration
    callback_url: Optional[str] = Field(
        default=None, 
        description="URL to call with status updates"
    )


class IngestionResponse(BaseModel):
    """Response after accepting an ingestion request."""
    job_id: str
    status: JobStatus
    message: str


class IngestionJobStatus(BaseModel):
    """Full status of an ingestion job."""
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: Optional[str] = None
    error: Optional[str] = None
    
    chunks_created: Optional[int] = None
    document_type: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class CallbackPayload(BaseModel):
    """Payload sent to backend on status change."""
    job_id: str
    status: str  # String to allow flexibility
    progress: int
    message: Optional[str] = None
    error: Optional[str] = None
    
    document_id: Optional[str] = None
    collection_name: Optional[str] = None
    document_type: Optional[str] = None
    chunks_created: Optional[int] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConnectorConfig(BaseModel):
    """Base configuration for data connectors."""
    connector_type: ConnectorType = Field(..., description="Type of connector")
    name: str = Field(..., description="Connector name")
    enabled: bool = Field(default=True)
    schedule: Optional[str] = Field(default=None, description="Cron schedule for automatic runs")
    config: Dict[str, Any] = Field(default_factory=dict, description="Connector-specific configuration")


class JobListResponse(BaseModel):
    """Response with list of jobs."""
    jobs: List[IngestionJobStatus]
    total: int
    skip: int
    limit: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    timestamp: datetime
    database: str = "connected"
    vector_service: str = "connected"
    active_jobs: int = 0
