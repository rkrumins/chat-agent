"""
Shared Schemas Package for Chat-Agent Microservices

This package provides common Pydantic models, enums, and interfaces
used across all microservices for consistent API communication.

Services using this package:
- backend (API Gateway)
- ingestion-service
- vector-service
"""

from .base import (
    JobStatus,
    ProcessingStatus,
    ChunkingStrategy,
    VectorDBType,
    EmbeddingProvider,
)

from .documents import (
    DocumentMetadata,
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    ChunkMetadata,
    ChunkResponse,
)

from .collections import (
    CollectionCreate,
    CollectionResponse,
    CollectionConfig,
    EmbeddingConfig,
)

from .ingestion import (
    IngestionRequest,
    IngestionResponse,
    IngestionJobStatus,
    CallbackPayload,
    ConnectorConfig,
    ConnectorType,
)

from .vector import (
    VectorStoreRequest,
    VectorSearchRequest,
    VectorSearchResult,
    VectorDeleteRequest,
)

__version__ = "1.0.0"

__all__ = [
    # Base enums
    "JobStatus",
    "ProcessingStatus", 
    "ChunkingStrategy",
    "VectorDBType",
    "EmbeddingProvider",
    # Documents
    "DocumentMetadata",
    "DocumentCreate",
    "DocumentUpdate",
    "DocumentResponse",
    "ChunkMetadata",
    "ChunkResponse",
    # Collections
    "CollectionCreate",
    "CollectionResponse",
    "CollectionConfig",
    "EmbeddingConfig",
    # Ingestion
    "IngestionRequest",
    "IngestionResponse",
    "IngestionJobStatus",
    "CallbackPayload",
    "ConnectorConfig",
    "ConnectorType",
    # Vector
    "VectorStoreRequest",
    "VectorSearchRequest",
    "VectorSearchResult",
    "VectorDeleteRequest",
]
