"""
Shared configuration settings for VectorDB Manager microservices.
All services import from here to ensure consistent configuration.
"""

import os
from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
UPLOADS_ROOT = PROJECT_ROOT / "uploads"
FILES_DIR = UPLOADS_ROOT / "files"
COLLECTIONS_DIR = UPLOADS_ROOT / "collections"

# Note: Directory creation moved to ensure_directories() function
def ensure_directories():
    """Create required directories. Call this at service startup, not import."""
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    COLLECTIONS_DIR.mkdir(parents=True, exist_ok=True)


# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "ingestion.db"))
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# ChromaDB
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(PROJECT_ROOT / "chroma_db"))

# Service URLs
BACKEND_HOST = os.getenv("BACKEND_HOST", "localhost")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

INGESTION_HOST = os.getenv("INGESTION_HOST", "localhost")
INGESTION_PORT = int(os.getenv("INGESTION_PORT", "8002"))
INGESTION_URL = f"http://{INGESTION_HOST}:{INGESTION_PORT}"

FRONTEND_HOST = os.getenv("FRONTEND_HOST", "localhost")
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "3000"))

# Embedding configuration
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", None)
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", None)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", None)

# Processing defaults
DEFAULT_CHUNK_SIZE = int(os.getenv("DEFAULT_CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "200"))
DEFAULT_CHUNKING_STRATEGY = os.getenv("DEFAULT_CHUNKING_STRATEGY", "semantic")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB

# Callback settings
CALLBACK_TIMEOUT = int(os.getenv("CALLBACK_TIMEOUT", "30"))  # seconds
CALLBACK_RETRY_ATTEMPTS = int(os.getenv("CALLBACK_RETRY_ATTEMPTS", "3"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
