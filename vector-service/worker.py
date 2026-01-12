"""
Background Worker Pool for Vector Service.
Processes queued embedding jobs in parallel worker threads.
Configurable worker count for scaling.
"""

import os
import json
import time
import logging
import threading
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

import httpx

from job_queue import get_job_queue, JobQueue
from job_models import JobStatus, JobCallback

logger = logging.getLogger(__name__)

# Configuration
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "2"))  # Number of parallel workers
WORKER_POLL_INTERVAL = float(os.getenv("WORKER_POLL_INTERVAL", "0.5"))
WORKER_BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "50"))


class WorkerPool:
    """
    Pool of background workers that process vector embedding jobs in parallel.
    Each worker runs in its own thread, polling the shared job queue.
    """
    
    def __init__(self, backend, embedding_fn, num_workers: int = None):
        """
        Initialize the worker pool.
        
        Args:
            backend: Vector database backend (ChromaDBBackend)
            embedding_fn: Embedding function for generating vectors
            num_workers: Number of parallel workers (default from WORKER_COUNT env)
        """
        self.backend = backend
        self.embedding_fn = embedding_fn
        self.num_workers = num_workers or WORKER_COUNT
        self.queue = get_job_queue()
        self._stop_event = threading.Event()
        self._workers: List[threading.Thread] = []
        self._lock = threading.Lock()  # For thread-safe operations
    
    def start(self):
        """Start all worker threads."""
        if self._workers:
            logger.warning("Worker pool already running")
            return
        
        # Recover any interrupted jobs from previous run
        recovered = self.queue.recover_interrupted_jobs()
        if recovered:
            logger.info(f"Recovered {recovered} interrupted jobs")
        
        self._stop_event.clear()
        
        # Start worker threads
        for i in range(self.num_workers):
            worker_name = f"VectorWorker-{i+1}"
            thread = threading.Thread(
                target=self._worker_loop,
                name=worker_name,
                args=(i,),
                daemon=True
            )
            self._workers.append(thread)
            thread.start()
            logger.info(f"Started {worker_name}")
        
        logger.info(f"Worker pool started with {self.num_workers} workers")
    
    def stop(self, timeout: float = 15.0):
        """Stop all worker threads gracefully."""
        if not self._workers:
            return
        
        logger.info(f"Stopping {len(self._workers)} workers...")
        self._stop_event.set()
        
        # Wait for all workers to stop
        for thread in self._workers:
            thread.join(timeout=timeout / len(self._workers))
            if thread.is_alive():
                logger.warning(f"{thread.name} did not stop gracefully")
            else:
                logger.debug(f"{thread.name} stopped")
        
        self._workers.clear()
        logger.info("Worker pool stopped")
    
    def is_running(self) -> bool:
        """Check if any workers are running."""
        return any(t.is_alive() for t in self._workers)
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker pool status."""
        return {
            "num_workers": self.num_workers,
            "active_workers": sum(1 for t in self._workers if t.is_alive()),
            "pending_jobs": self.queue.get_pending_count(),
            "running": self.is_running()
        }
    
    def _worker_loop(self, worker_id: int):
        """Main loop for a single worker thread."""
        worker_name = f"Worker-{worker_id + 1}"
        logger.info(f"{worker_name}: Started, polling for jobs...")
        
        while not self._stop_event.is_set():
            try:
                # Try to get a job (thread-safe dequeue)
                job = self.queue.dequeue()
                
                if job is None:
                    # No jobs available, sleep and retry
                    time.sleep(WORKER_POLL_INTERVAL)
                    continue
                
                # Process the job
                logger.info(f"{worker_name}: Picked up job {job['id']}")
                self._process_job(job, worker_name)
                
            except Exception as e:
                logger.error(f"{worker_name}: Error in worker loop: {e}", exc_info=True)
                time.sleep(WORKER_POLL_INTERVAL)
        
        logger.info(f"{worker_name}: Stopped")
    
    def _process_job(self, job: Dict[str, Any], worker_name: str):
        """Process a single job."""
        job_id = job['id']
        collection_name = job['collection_name']
        documents = job['documents']
        callback_url = job.get('callback_url')
        batch_size = job.get('batch_size', WORKER_BATCH_SIZE)
        
        total_docs = len(documents)
        processed = 0
        
        logger.info(f"{worker_name}: Processing job {job_id} - {total_docs} docs in '{collection_name}'")
        
        try:
            # Get collection directly from backend's client (thread-safe)
            with self._lock:
                col = self.backend.client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=self.embedding_fn
                )
            
            # Process in batches
            for i in range(0, total_docs, batch_size):
                if self._stop_event.is_set():
                    logger.info(f"{worker_name}: Job {job_id} interrupted by shutdown")
                    return
                
                batch = documents[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (total_docs + batch_size - 1) // batch_size
                
                logger.info(f"{worker_name}: Job {job_id} batch {batch_num}/{total_batches} ({len(batch)} docs)")
                
                # Extract content and metadata
                ids = [doc['id'] for doc in batch]
                contents = [doc['content'] for doc in batch]
                
                # Prepare metadata for ChromaDB
                metadatas = []
                for doc in batch:
                    metadata = doc.get('metadata', {})
                    chroma_meta = {}
                    for key, value in metadata.items():
                        if isinstance(value, list):
                            chroma_meta[key] = ", ".join(str(v) for v in value)
                        elif isinstance(value, dict):
                            chroma_meta[key] = json.dumps(value)
                        elif isinstance(value, (str, int, float, bool)) or value is None:
                            chroma_meta[key] = value
                        else:
                            chroma_meta[key] = str(value)
                    metadatas.append(chroma_meta)
                
                # Store in ChromaDB (upsert to handle existing docs)
                try:
                    col.upsert(
                        ids=ids,
                        documents=contents,
                        metadatas=metadatas
                    )
                except Exception as e:
                    logger.warning(f"{worker_name}: Upsert failed, trying add: {e}")
                    col.add(
                        ids=ids,
                        documents=contents,
                        metadatas=metadatas
                    )
                
                # Update progress
                processed = min(i + batch_size, total_docs)
                self.queue.update_progress(job_id, processed)
                
                # Send progress callback if URL provided
                if callback_url:
                    self._send_callback(
                        callback_url, job_id, JobStatus.PROCESSING,
                        processed, total_docs
                    )
            
            # Job completed successfully
            self.queue.complete_job(job_id)
            
            if callback_url:
                self._send_callback(
                    callback_url, job_id, JobStatus.COMPLETED,
                    total_docs, total_docs
                )
            
            logger.info(f"{worker_name}: Job {job_id} completed - {total_docs} docs stored")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{worker_name}: Job {job_id} failed: {error_msg}", exc_info=True)
            self.queue.fail_job(job_id, error_msg)
            
            if callback_url:
                self._send_callback(
                    callback_url, job_id, JobStatus.FAILED,
                    processed, total_docs, error_msg
                )
    
    def _send_callback(
        self,
        url: str,
        job_id: str,
        status: JobStatus,
        processed: int,
        total: int,
        error: Optional[str] = None
    ):
        """Send progress callback to the specified URL."""
        try:
            progress = (processed / total * 100) if total > 0 else 0
            
            payload = JobCallback(
                job_id=job_id,
                status=status,
                progress_percent=progress,
                processed_count=processed,
                total_documents=total,
                error_message=error
            )
            
            with httpx.Client() as client:
                response = client.post(
                    url,
                    json=payload.model_dump(mode='json'),
                    timeout=10.0
                )
                if response.status_code != 200:
                    logger.warning(f"Callback failed: {response.status_code}")
                    
        except Exception as e:
            logger.debug(f"Failed to send callback: {e}")


# Singleton pool instance
_pool_instance: Optional[WorkerPool] = None


def get_worker() -> Optional[WorkerPool]:
    """Get the singleton worker pool instance."""
    return _pool_instance


def init_worker(backend, embedding_fn, num_workers: int = None) -> WorkerPool:
    """Initialize and start the worker pool."""
    global _pool_instance
    
    if _pool_instance is not None:
        _pool_instance.stop()
    
    _pool_instance = WorkerPool(backend, embedding_fn, num_workers)
    _pool_instance.start()
    
    return _pool_instance


def stop_worker():
    """Stop the worker pool."""
    global _pool_instance
    
    if _pool_instance is not None:
        _pool_instance.stop()
        _pool_instance = None
