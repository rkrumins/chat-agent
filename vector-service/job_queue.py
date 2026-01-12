"""
SQLite-backed Job Queue for Vector Service.
Provides persistent job storage that survives service restarts.
"""

import os
import json
import uuid
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from job_models import JobStatus

logger = logging.getLogger(__name__)

# Database path
QUEUE_DB_PATH = os.getenv("VECTOR_QUEUE_DB", "./vector_queue.db")


class JobQueue:
    """
    SQLite-backed persistent job queue.
    Thread-safe with connection pooling.
    """
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or QUEUE_DB_PATH
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA foreign_keys=ON")
        return self._local.connection
    
    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def _init_db(self):
        """Initialize the job queue database schema."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_jobs (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    total_documents INTEGER NOT NULL,
                    processed_count INTEGER DEFAULT 0,
                    documents_json TEXT NOT NULL,
                    error_message TEXT,
                    callback_url TEXT,
                    batch_size INTEGER DEFAULT 50,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            # Index for status queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_status 
                ON vector_jobs(status)
            """)
            
            logger.info(f"Job queue database initialized at {self.db_path}")
    
    def enqueue(
        self,
        collection_name: str,
        documents: List[Dict[str, Any]],
        callback_url: Optional[str] = None,
        batch_size: int = 50
    ) -> str:
        """
        Add a new job to the queue.
        Returns the job ID.
        """
        job_id = str(uuid.uuid4())
        documents_json = json.dumps(documents)
        
        with self._transaction() as conn:
            conn.execute("""
                INSERT INTO vector_jobs 
                (id, collection_name, status, total_documents, documents_json, callback_url, batch_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id,
                collection_name,
                JobStatus.PENDING.value,
                len(documents),
                documents_json,
                callback_url,
                batch_size
            ))
        
        logger.info(f"Enqueued job {job_id} with {len(documents)} documents")
        return job_id
    
    def dequeue(self) -> Optional[Dict[str, Any]]:
        """
        Get the next pending job and mark it as processing.
        Returns None if no jobs available.
        """
        with self._transaction() as conn:
            # Get oldest pending job
            cursor = conn.execute("""
                SELECT * FROM vector_jobs 
                WHERE status = ? 
                ORDER BY created_at ASC 
                LIMIT 1
            """, (JobStatus.PENDING.value,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            job = dict(row)
            job_id = job['id']
            
            # Mark as processing
            conn.execute("""
                UPDATE vector_jobs 
                SET status = ?, started_at = ?
                WHERE id = ?
            """, (JobStatus.PROCESSING.value, datetime.utcnow(), job_id))
            
            # Parse documents JSON
            job['documents'] = json.loads(job['documents_json'])
            del job['documents_json']
            
            logger.info(f"Dequeued job {job_id} for processing")
            return job
    
    def update_progress(self, job_id: str, processed_count: int):
        """Update the progress of a job."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE vector_jobs 
                SET processed_count = ?
                WHERE id = ?
            """, (processed_count, job_id))
    
    def complete_job(self, job_id: str):
        """Mark a job as completed."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                SELECT total_documents FROM vector_jobs WHERE id = ?
            """, (job_id,))
            row = cursor.fetchone()
            total = row['total_documents'] if row else 0
            
            conn.execute("""
                UPDATE vector_jobs 
                SET status = ?, processed_count = ?, completed_at = ?
                WHERE id = ?
            """, (JobStatus.COMPLETED.value, total, datetime.utcnow(), job_id))
        
        logger.info(f"Job {job_id} completed")
    
    def fail_job(self, job_id: str, error_message: str):
        """Mark a job as failed."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE vector_jobs 
                SET status = ?, error_message = ?, completed_at = ?
                WHERE id = ?
            """, (JobStatus.FAILED.value, error_message, datetime.utcnow(), job_id))
        
        logger.error(f"Job {job_id} failed: {error_message}")
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending job.
        Returns True if cancelled, False if not found or already processing.
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE vector_jobs 
                SET status = ?, completed_at = ?
                WHERE id = ? AND status = ?
            """, (JobStatus.CANCELLED.value, datetime.utcnow(), job_id, JobStatus.PENDING.value))
            
            return cursor.rowcount > 0
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT id, collection_name, status, total_documents, processed_count,
                   error_message, callback_url, created_at, started_at, completed_at
            FROM vector_jobs WHERE id = ?
        """, (job_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        job = dict(row)
        # Calculate progress
        if job['total_documents'] > 0:
            job['progress_percent'] = (job['processed_count'] / job['total_documents']) * 100
        else:
            job['progress_percent'] = 0
        
        return job
    
    def get_pending_count(self) -> int:
        """Get count of pending jobs."""
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT COUNT(*) FROM vector_jobs WHERE status = ?
        """, (JobStatus.PENDING.value,))
        return cursor.fetchone()[0]
    
    def recover_interrupted_jobs(self):
        """
        Reset any 'processing' jobs back to 'pending'.
        Called on startup to handle jobs interrupted by restart.
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE vector_jobs 
                SET status = ?, started_at = NULL
                WHERE status = ?
            """, (JobStatus.PENDING.value, JobStatus.PROCESSING.value))
            
            recovered = cursor.rowcount
            if recovered > 0:
                logger.info(f"Recovered {recovered} interrupted jobs")
            
            return recovered
    
    def cleanup_old_jobs(self, days: int = 7):
        """Remove completed/failed jobs older than specified days."""
        with self._transaction() as conn:
            cursor = conn.execute("""
                DELETE FROM vector_jobs 
                WHERE status IN (?, ?, ?)
                AND completed_at < datetime('now', ?)
            """, (
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                f'-{days} days'
            ))
            
            deleted = cursor.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old jobs")
            
            return deleted


# Singleton instance
_queue_instance: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get the singleton job queue instance."""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = JobQueue()
    return _queue_instance
