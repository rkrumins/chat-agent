# Chatbot Configuration Guide

This guide explains how to configure the RAG chatbot by modifying the `config.py` file.

## Quick Start

All configuration values are in `chatbot/config.py`. You can either:

1. **Modify `config.py` directly** - Edit the values in the file
2. **Use environment variables** - Set them before running (overrides config.py)

## Configuration Options

### Backend API Configuration

```python
BACKEND_API_URL = "http://localhost:8000"  # Backend API URL
BACKEND_API_TIMEOUT = 30                    # Request timeout in seconds
```

### LLM Configuration

```python
LLM_PROVIDER = "groq"                       # Options: "groq", "gemini", "openai"
MODEL_NAME = "llama-3.1-8b-instant"        # Model name (varies by provider)
TEMPERATURE = 0.7                           # 0.0-1.0 (Lower = accurate, Higher = creative)
MAX_TOKENS = 2048                           # Maximum response length
```

### Embedding Configuration

```python
EMBEDDING_PROVIDER = "sentence-transformers"  # Options: "sentence-transformers", "gemini"
EMBEDDING_MODEL = "all-mpnet-base-v2"        # Model name (varies by provider)
GOOGLE_APPLICATION_CREDENTIALS = None        # Path to GCP service account JSON (for Gemini)
```

**Embedding Providers:**

- **sentence-transformers** (default):
  - `all-mpnet-base-v2` (768 dimensions, recommended)
  - `all-MiniLM-L6-v2` (384 dimensions, faster)

- **gemini**:
  - `models/embedding-001` (768 dimensions)
  - `models/text-embedding-004` (768 dimensions, latest)
  - Requires GCP service account key or Google API key
  - See `GEMINI_EMBEDDING_SETUP.md` for detailed setup

**Available Models:**

- **Groq:**
  - `llama-3.1-8b-instant` (recommended - fast)
  - `llama-3.1-70b-versatile` (more capable)
  - `mixtral-8x7b-32768`
  - `llama2-70b-4096`

- **Gemini:**
  - `gemini-pro`
  - `gemini-pro-vision`

- **OpenAI:**
  - `gpt-4`
  - `gpt-3.5-turbo`
  - `gpt-4-turbo-preview`

### Retrieval Configuration

```python
MAX_RESULTS_PER_COLLECTION = 8              # Max results per collection
MAX_TOTAL_RESULTS = 30                      # Max total results across all collections
MIN_SIMILARITY_SCORE = 0.3                  # Minimum similarity threshold (0.0-1.0)
```

**Tuning Tips:**
- **More results**: Increase `MAX_RESULTS_PER_COLLECTION` and `MAX_TOTAL_RESULTS` for comprehensive answers
- **Better quality**: Increase `MIN_SIMILARITY_SCORE` to filter out less relevant results
- **Faster responses**: Decrease these values for quicker answers

### Feature Flags

```python
ENABLE_RERANKING = True                     # Enable reranking for better relevance
ENABLE_QUERY_REWRITING = True               # Enable query rewriting for better retrieval
ENABLE_MULTI_QUERY = True                   # Enable multi-query retrieval
```

**Recommendations:**
- Keep all enabled for best accuracy
- Disable for faster responses (less accurate)

### Collection Configuration

```python
DEFAULT_COLLECTIONS = []                    # Empty = query all collections
                                           # Example: ["collection1", "collection2"]
```

**Examples:**
- `[]` - Query all collections (default)
- `["policies"]` - Only query "policies" collection
- `["policies", "hr-docs"]` - Query both collections

## Using Environment Variables

You can override any config value using environment variables:

```bash
export LLM_PROVIDER=groq
export MODEL_NAME=llama-3.1-8b-instant
export TEMPERATURE=0.7
export MAX_RESULTS_PER_COLLECTION=8
export MAX_TOTAL_RESULTS=30
export GROQ_API_KEY=your_api_key_here
```

Then run the chatbot:
```bash
chainlit run rag_chatbot.py
```

## API Keys

API keys should be set via environment variables for security:

```bash
# Groq (recommended - free tier available)
export GROQ_API_KEY=your_groq_api_key

# Google Gemini (for LLM)
export GOOGLE_API_KEY=your_google_api_key

# Google Gemini (for Embeddings - use service account or API key)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
# OR
export GOOGLE_API_KEY=your_google_api_key

# OpenAI
export OPENAI_API_KEY=your_openai_api_key
```

**For Gemini Embeddings:**
- **Recommended:** Use GCP service account key file (set `GOOGLE_APPLICATION_CREDENTIALS`)
- **Alternative:** Use Google API key (set `GOOGLE_API_KEY`)
- See `GEMINI_EMBEDDING_SETUP.md` for detailed instructions

Get API keys:
- **Groq**: https://console.groq.com/keys (FREE)
- **Gemini**: https://makersuite.google.com/app/apikey
- **OpenAI**: https://platform.openai.com/api-keys

## Example Configurations

### High Accuracy (Recommended)

```python
TEMPERATURE = 0.7
MAX_RESULTS_PER_COLLECTION = 8
MAX_TOTAL_RESULTS = 30
MIN_SIMILARITY_SCORE = 0.3
ENABLE_RERANKING = True
ENABLE_QUERY_REWRITING = True
ENABLE_MULTI_QUERY = True
```

### Fast Responses

```python
TEMPERATURE = 0.5
MAX_RESULTS_PER_COLLECTION = 5
MAX_TOTAL_RESULTS = 15
MIN_SIMILARITY_SCORE = 0.4
ENABLE_RERANKING = False
ENABLE_QUERY_REWRITING = False
ENABLE_MULTI_QUERY = False
```

### Maximum Coverage

```python
TEMPERATURE = 0.7
MAX_RESULTS_PER_COLLECTION = 15
MAX_TOTAL_RESULTS = 50
MIN_SIMILARITY_SCORE = 0.2
ENABLE_RERANKING = True
ENABLE_QUERY_REWRITING = True
ENABLE_MULTI_QUERY = True
```

## Validation

The configuration is automatically validated on startup. If there are errors, you'll see warnings in the logs. Common issues:

- Missing API key for selected provider
- Invalid temperature (must be 0.0-1.0)
- Invalid similarity score (must be 0.0-1.0)
- MAX_RESULTS_PER_COLLECTION > MAX_TOTAL_RESULTS

## Viewing Current Configuration

Use the `/info` command in the chatbot to see current configuration values.

