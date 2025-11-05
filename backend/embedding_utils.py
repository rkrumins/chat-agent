"""
Embedding utilities for supporting multiple embedding providers
Supports sentence-transformers and Google Gemini embeddings
"""

import os
import logging
from typing import Optional
import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)


def get_embedding_function(provider: str = None, model_name: str = None, 
                          service_account_path: Optional[str] = None):
    """
    Get embedding function based on provider
    
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
            # Set environment variable for Google auth
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_path
            logger.info(f"Using GCP service account from: {service_account_path}")
        else:
            # Try using API key if available
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                os.environ["GOOGLE_API_KEY"] = api_key
                logger.info("Using Google API key for Gemini embeddings")
            else:
                logger.warning(
                    "No authentication method found for Gemini embeddings. "
                    "Set GOOGLE_APPLICATION_CREDENTIALS (service account path) "
                    "or GOOGLE_API_KEY environment variable."
                )
        
        try:
            # Try to use GoogleGenerativeAIEmbeddingFunction if available
            # This requires chromadb to support it, which may not be available in all versions
            # Fallback: we'll create a custom embedding function
            logger.info(f"Using Gemini embedding model: {model}")
            
            # For now, we'll use a custom implementation
            # ChromaDB's embedding_functions might not have Gemini support directly
            # So we'll create a wrapper
            return create_gemini_embedding_function(model, service_account_path)
            
        except Exception as e:
            logger.error(f"Error initializing Gemini embeddings: {str(e)}")
            raise ValueError(f"Failed to initialize Gemini embeddings: {str(e)}")
    
    else:
        raise ValueError(f"Unknown embedding provider: {provider}. Must be 'sentence-transformers' or 'gemini'")


def create_gemini_embedding_function(model_name: str, service_account_path: Optional[str] = None):
    """
    Create a custom embedding function for Gemini
    
    This wraps Google's Generative AI embedding API
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
        # Try API key
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            logger.info("Authenticated with Google API key")
        else:
            # Try default credentials
            try:
                credentials, project = google.auth.default()
                genai.configure(credentials=credentials)
                logger.info("Using default Google Cloud credentials")
            except Exception as e:
                raise ValueError(
                    "No authentication method found. Set GOOGLE_APPLICATION_CREDENTIALS "
                    "or GOOGLE_API_KEY environment variable."
                )
    
    # Create embedding function
    class GeminiEmbeddingFunction(embedding_functions.EmbeddingFunction):
        def __init__(self, model_name: str):
            self.model_name = model_name
        
        def __call__(self, input_texts):
            """Generate embeddings using Gemini"""
            try:
                # Handle both single string and list of strings
                if isinstance(input_texts, str):
                    input_texts = [input_texts]
                
                # Generate embeddings - batch processing for efficiency
                embeddings = []
                for text in input_texts:
                    result = genai.embed_content(
                        model=self.model_name,
                        content=text,
                        task_type="retrieval_document"  # Use "retrieval_query" for queries
                    )
                    
                    # Extract embedding from result
                    # The API returns a dict with 'embedding' key containing a list
                    if isinstance(result, dict):
                        embedding = result.get('embedding')
                        if embedding:
                            embeddings.append(embedding)
                        else:
                            # Fallback: try different key names
                            embedding = result.get('values') or result.get('embedding_vector')
                            if embedding:
                                embeddings.append(embedding)
                            else:
                                # Last resort: use the dict itself
                                logger.warning(f"Unexpected result format: {result.keys()}")
                                embeddings.append(result)
                    elif isinstance(result, list):
                        # Direct list of embeddings
                        embeddings.extend(result if isinstance(result[0], list) else [result])
                    else:
                        embeddings.append(result)
                
                # Return in format expected by ChromaDB
                # ChromaDB expects a list of lists (one embedding per input)
                return embeddings if len(embeddings) > 1 else (embeddings[0] if embeddings else [])
                    
            except Exception as e:
                logger.error(f"Error generating Gemini embeddings: {str(e)}")
                raise
    
    return GeminiEmbeddingFunction(model_name)

