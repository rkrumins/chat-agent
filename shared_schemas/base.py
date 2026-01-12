"""
Base enums and types used across all services.
"""

from enum import Enum


class JobStatus(str, Enum):
    """Status of an ingestion job."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    """Alias for JobStatus used in backend for backwards compatibility."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChunkingStrategy(str, Enum):
    """Available chunking strategies for document processing."""
    SEMANTIC = "semantic"      # Smart semantic chunking (default, best for most cases)
    SIZE = "size"              # Character-based chunking with size limit
    LINES = "lines"            # Line-based chunking (one line per chunk)
    PARAGRAPHS = "paragraphs"  # Paragraph-based chunking
    SENTENCES = "sentences"    # Sentence-based chunking
    CUSTOM = "custom"          # Custom separator-based chunking


class VectorDBType(str, Enum):
    """Supported vector database backends."""
    CHROMADB = "chromadb"
    PGVECTOR = "pgvector"
    # Future: PINECONE, WEAVIATE, MILVUS, QDRANT


class EmbeddingProvider(str, Enum):
    """Supported embedding model providers."""
    SENTENCE_TRANSFORMERS = "sentence-transformers"
    GEMINI = "gemini"
    OPENAI = "openai"  # Future support
