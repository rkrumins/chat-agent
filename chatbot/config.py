"""
Configuration file for RAG Chatbot

This file contains all configurable settings for the chatbot.
Modify values here to change the default behavior.

To override with environment variables, set them before running:
  export LLM_PROVIDER=groq
  export TEMPERATURE=0.7
  etc.
"""

import os
from typing import List, Optional


class ChatbotConfig:
    """Configuration class for RAG Chatbot"""
    
    # ========================================================================
    # BACKEND API CONFIGURATION
    # ========================================================================
    
    # Backend API URL
    BACKEND_API_URL: str = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    
    # API request timeout in seconds
    BACKEND_API_TIMEOUT: int = int(os.getenv("BACKEND_API_TIMEOUT", "30"))
    
    # ========================================================================
    # LLM CONFIGURATION
    # ========================================================================
    
    # LLM Provider: "groq", "gemini", or "openai"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    
    # Model name (varies by provider)
    # Groq: "llama-3.1-8b-instant", "mixtral-8x7b-32768", "llama2-70b-4096"
    # Gemini: "gemini-pro", "gemini-pro-vision"
    # OpenAI: "gpt-4", "gpt-3.5-turbo", "gpt-4-turbo-preview"
    MODEL_NAME: str = os.getenv("MODEL_NAME", "llama-3.1-8b-instant")
    
    # Temperature (0.0-1.0): Lower = more focused/accurate, Higher = more creative
    # Recommended: 0.7 for balanced, 0.1-0.3 for accuracy, 0.8-1.0 for creativity
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
    
    # Maximum tokens in response
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "2048"))
    
    # ========================================================================
    # RETRIEVAL CONFIGURATION
    # ========================================================================
    
    # Maximum number of results to retrieve per collection
    MAX_RESULTS_PER_COLLECTION: int = int(os.getenv("MAX_RESULTS_PER_COLLECTION", "8"))
    
    # Maximum total results across all collections
    MAX_TOTAL_RESULTS: int = int(os.getenv("MAX_TOTAL_RESULTS", "30"))
    
    # Minimum similarity score threshold (0.0-1.0)
    # Results below this score will be filtered out
    MIN_SIMILARITY_SCORE: float = float(os.getenv("MIN_SIMILARITY_SCORE", "0.3"))
    
    # ========================================================================
    # FEATURE FLAGS
    # ========================================================================
    
    # Enable reranking for better relevance
    ENABLE_RERANKING: bool = os.getenv("ENABLE_RERANKING", "true").lower() == "true"
    
    # Enable query rewriting for better retrieval
    ENABLE_QUERY_REWRITING: bool = os.getenv("ENABLE_QUERY_REWRITING", "true").lower() == "true"
    
    # Enable multi-query retrieval (generate multiple query variations)
    ENABLE_MULTI_QUERY: bool = os.getenv("ENABLE_MULTI_QUERY", "true").lower() == "true"
    
    # ========================================================================
    # COLLECTION CONFIGURATION
    # ========================================================================
    
    # Default collections to query (comma-separated)
    # Empty string = query all collections
    # Example: "collection1,collection2" = only query these collections
    DEFAULT_COLLECTIONS: List[str] = [
        c.strip() for c in os.getenv("DEFAULT_COLLECTIONS", "").split(",") if c.strip()
    ]
    
    # ========================================================================
    # API KEYS (Set via environment variables for security)
    # ========================================================================
    
    # Groq API Key
    GROQ_API_KEY: Optional[str] = os.getenv("GROQ_API_KEY")
    
    # Google Gemini API Key
    GOOGLE_API_KEY: Optional[str] = os.getenv("GOOGLE_API_KEY")
    
    # OpenAI API Key
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    @classmethod
    def get_config_summary(cls) -> dict:
        """Get a summary of current configuration"""
        return {
            "backend_api_url": cls.BACKEND_API_URL,
            "llm_provider": cls.LLM_PROVIDER.upper(),
            "model_name": cls.MODEL_NAME,
            "temperature": cls.TEMPERATURE,
            "max_tokens": cls.MAX_TOKENS,
            "max_results_per_collection": cls.MAX_RESULTS_PER_COLLECTION,
            "max_total_results": cls.MAX_TOTAL_RESULTS,
            "min_similarity_score": cls.MIN_SIMILARITY_SCORE,
            "enable_reranking": cls.ENABLE_RERANKING,
            "enable_query_rewriting": cls.ENABLE_QUERY_REWRITING,
            "enable_multi_query": cls.ENABLE_MULTI_QUERY,
            "default_collections": cls.DEFAULT_COLLECTIONS if cls.DEFAULT_COLLECTIONS else "All collections",
        }
    
    @classmethod
    def validate(cls) -> List[str]:
        """Validate configuration and return list of errors (empty if valid)"""
        errors = []
        
        # Validate LLM provider
        if cls.LLM_PROVIDER not in ["groq", "gemini", "openai"]:
            errors.append(f"Invalid LLM_PROVIDER: {cls.LLM_PROVIDER}. Must be 'groq', 'gemini', or 'openai'")
        
        # Validate API keys
        if cls.LLM_PROVIDER == "groq" and not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is required when using Groq provider")
        elif cls.LLM_PROVIDER == "gemini" and not cls.GOOGLE_API_KEY:
            errors.append("GOOGLE_API_KEY is required when using Gemini provider")
        elif cls.LLM_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when using OpenAI provider")
        
        # Validate temperature
        if not 0.0 <= cls.TEMPERATURE <= 1.0:
            errors.append(f"TEMPERATURE must be between 0.0 and 1.0, got {cls.TEMPERATURE}")
        
        # Validate similarity score
        if not 0.0 <= cls.MIN_SIMILARITY_SCORE <= 1.0:
            errors.append(f"MIN_SIMILARITY_SCORE must be between 0.0 and 1.0, got {cls.MIN_SIMILARITY_SCORE}")
        
        # Validate retrieval settings
        if cls.MAX_RESULTS_PER_COLLECTION < 1:
            errors.append(f"MAX_RESULTS_PER_COLLECTION must be at least 1, got {cls.MAX_RESULTS_PER_COLLECTION}")
        
        if cls.MAX_TOTAL_RESULTS < 1:
            errors.append(f"MAX_TOTAL_RESULTS must be at least 1, got {cls.MAX_TOTAL_RESULTS}")
        
        if cls.MAX_RESULTS_PER_COLLECTION > cls.MAX_TOTAL_RESULTS:
            errors.append(
                f"MAX_RESULTS_PER_COLLECTION ({cls.MAX_RESULTS_PER_COLLECTION}) "
                f"cannot be greater than MAX_TOTAL_RESULTS ({cls.MAX_TOTAL_RESULTS})"
            )
        
        return errors


# Create a global config instance
config = ChatbotConfig()

