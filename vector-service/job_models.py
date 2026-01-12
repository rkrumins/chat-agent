"""
Job Queue Models - Pydantic models for async job processing.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class JobStatus(str, Enum):
    """Status of a vector processing job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VectorJobCreate(BaseModel):
    """Request to create a new vector processing job."""
    collection_name: str
    documents: List[Dict[str, Any]]
    callback_url: Optional[str] = None
    batch_size: int = 50  # Process in batches of this size


class VectorJobResponse(BaseModel):
    """Response when a job is created."""
    job_id: str
    status: JobStatus
    message: str
    total_documents: int


class VectorJobStatus(BaseModel):
    """Detailed status of a job."""
    job_id: str
    status: JobStatus
    collection_name: str
    total_documents: int
    processed_count: int
    progress_percent: float
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobCallback(BaseModel):
    """Callback payload sent to ingestion service."""
    job_id: str
    status: JobStatus
    progress_percent: float
    processed_count: int
    total_documents: int
    error_message: Optional[str] = None
