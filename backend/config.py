"""
Configuration management for VectorDB Manager backend
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", str(BASE_DIR / "chroma_db"))

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# CORS Configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Document Processing Configuration
DEFAULT_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))

# Task Configuration
TASK_STATUS_RETENTION_SECONDS = int(os.getenv("TASK_STATUS_RETENTION_SECONDS", "3600"))

class Settings:
    """Application settings"""
    
    # Database
    CHROMA_DB_PATH: str = CHROMA_DB_PATH
    
    # API
    API_TITLE: str = "VectorDB Management API"
    API_VERSION: str = "1.0.0"
    API_HOST: str = API_HOST
    API_PORT: int = API_PORT
    
    # CORS
    CORS_ORIGINS: list = CORS_ORIGINS
    
    # Processing
    CHUNK_SIZE: int = DEFAULT_CHUNK_SIZE
    CHUNK_OVERLAP: int = DEFAULT_CHUNK_OVERLAP
    
    # Tasks
    TASK_RETENTION: int = TASK_STATUS_RETENTION_SECONDS


settings = Settings()

