"""
Embedding utilities for vector-service.
Supports multiple embedding providers: sentence-transformers, Gemini, etc.
Consolidated from backend/embedding_utils.py
"""

import os
import logging
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


def get_embedding_function(
    provider: str = None,
    model_name: str = None,
    service_account_path: Optional[str] = None
):
    """
    Get embedding function based on provider.
    
    Args:
        provider: "sentence-transformers" or "gemini"
        model_name: Model name (varies by provider)
        service_account_path: Path to GCP service account JSON key file (for Gemini)
    
    Returns:
        ChromaDB embedding function
    """
    provider = provider or os.getenv("EMBEDDING_PROVIDER", "sentence-transformers")
    model_name = model_name or os.getenv("EMBEDDING_MODEL", None)
    
    if provider == "sentence-transformers":
        # Default to all-mpnet-base-v2 if not specified
        model = model_name or "sentence-transformers/all-mpnet-base-v2"
        logger.info(f"Using sentence-transformers embedding: {model}")
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=model
        )
    
    elif provider == "gemini":
        # Use Gemini embeddings
        model = model_name or "models/embedding-001"
        
        # Set up authentication
        service_account_path = service_account_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        
        if service_account_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_path
            logger.info(f"Using GCP service account from: {service_account_path}")
        else:
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key
                logger.info("Using Google API key for Gemini embeddings")
            else:
                logger.warning(
                    "No authentication method found for Gemini embeddings. "
                    "Set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_API_KEY."
                )
        
        try:
            logger.info(f"Using Gemini embedding model: {model}")
            return create_gemini_embedding_function(model, service_account_path)
        except Exception as e:
            logger.error(f"Error initializing Gemini embeddings: {str(e)}")
            raise ValueError(f"Failed to initialize Gemini embeddings: {str(e)}")
    
    else:
        raise ValueError(
            f"Unknown embedding provider: {provider}. "
            "Must be 'sentence-transformers' or 'gemini'"
        )


def create_gemini_embedding_function(
    model_name: str,
    service_account_path: Optional[str] = None
):
    """
    Create a custom embedding function for Gemini.
    Wraps Google's Generative AI embedding API.
    """
    try:
        import google.generativeai as genai
        from google.oauth2 import service_account
        import google.auth
    except ImportError:
        raise ImportError(
            "Google Generative AI libraries not installed. "
            "Install with: pip install google-generativeai google-auth"
        )
    
    # Authenticate
    if service_account_path and os.path.exists(service_account_path):
        credentials = service_account.Credentials.from_service_account_file(
            service_account_path,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        genai.configure(credentials=credentials)
        logger.info("Authenticated with GCP service account")
    else:
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            logger.info("Authenticated with Google API key")
        else:
            try:
                credentials, project = google.auth.default()
                genai.configure(credentials=credentials)
                logger.info("Using default Google Cloud credentials")
            except Exception:
                raise ValueError(
                    "No authentication method found. "
                    "Set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_API_KEY."
                )
    
    class GeminiEmbeddingFunction(embedding_functions.EmbeddingFunction):
        def __init__(self, model_name: str):
            self.model_name = model_name
        
        def __call__(self, input_texts):
            """Generate embeddings using Gemini."""
            try:
                if isinstance(input_texts, str):
                    input_texts = [input_texts]
                
                embeddings = []
                for text in input_texts:
                    result = genai.embed_content(
                        model=self.model_name,
                        content=text,
                        task_type="retrieval_document"
                    )
                    
                    if isinstance(result, dict):
                        embedding = result.get('embedding')
                        if embedding:
                            embeddings.append(embedding)
                        else:
                            embedding = result.get('values') or result.get('embedding_vector')
                            if embedding:
                                embeddings.append(embedding)
                            else:
                                logger.warning(f"Unexpected result format: {result.keys()}")
                                embeddings.append(result)
                    elif isinstance(result, list):
                        embeddings.extend(result if isinstance(result[0], list) else [result])
                    else:
                        embeddings.append(result)
                
                return embeddings if len(embeddings) > 1 else (embeddings[0] if embeddings else [])
                    
            except Exception as e:
                logger.error(f"Error generating Gemini embeddings: {str(e)}")
                raise
    
    return GeminiEmbeddingFunction(model_name)


def get_embedding_dimension(embedding_function) -> int:
    """Get the dimension of embeddings from a function."""
    try:
        test_embedding = embedding_function(["test"])
        if isinstance(test_embedding, list):
            if isinstance(test_embedding[0], list):
                return len(test_embedding[0])
            return len(test_embedding)
        return 768  # Default
    except Exception:
        return 768  # Default for most models
