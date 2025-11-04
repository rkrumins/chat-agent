# RAG Module for Multi-Collection Vector Database Queries

## Overview

This is a production-ready RAG (Retrieval-Augmented Generation) module that enables querying documents across multiple collections in your Vector Database. It's built for Python 3.12 and integrates seamlessly with Chainlit.

## Features

- **Multi-Collection Support**: Query across one or multiple collections simultaneously
- **Backend API Integration**: Uses the backend API instead of direct database access (better separation of concerns)
- **Large-Scale Optimization**: Handles 100s of documents per collection efficiently
- **Smart Retrieval**: Semantic search with automatic reranking
- **Production-Ready**: Comprehensive error handling, logging, and async support
- **Chainlit Integration**: Ready-to-use Chainlit chatbot interface

## Architecture

```
User Question
     ↓
Chainlit Interface (rag_chatbot.py)
     ↓
RAG Session Manager
     ↓
RAG Engine
     ↓
VectorDB Client (HTTP API)
     ↓
Backend API (FastAPI)
     ↓
ChromaDB Vector Database
     ↓
Retrieved Documents (Multi-Collection)
     ↓
Reranking & Context Formatting
     ↓
LLM (Groq/Gemini/OpenAI)
     ↓
Generated Answer + Sources
```

## Files

### `rag_module.py`
Core RAG module containing:
- `VectorDBClient`: HTTP client for backend API interactions
- `RAGEngine`: Main RAG engine with retrieval and generation
- `RAGSessionManager`: Session management for Chainlit integration
- `RetrievalResult`: Data class for retrieval results
- `RAGResponse`: Data class for complete RAG responses

### `rag_chatbot.py`
Chainlit application that uses the RAG module:
- User interface with commands
- Session management
- Multi-collection query support
- Source citation display

## Installation

### 1. Install Dependencies

```bash
cd chatbot
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file or set environment variables:

```env
# Backend API Configuration
BACKEND_API_URL=http://localhost:8000
BACKEND_API_TIMEOUT=30

# LLM Configuration
LLM_PROVIDER=groq  # or gemini, openai
GROQ_API_KEY=your_api_key_here
MODEL_NAME=mixtral-8x7b-32768
TEMPERATURE=0.1
MAX_TOKENS=2048

# RAG Configuration
MAX_RESULTS_PER_COLLECTION=10
MAX_TOTAL_RESULTS=50
MIN_SIMILARITY_SCORE=0.3
ENABLE_RERANKING=true

# Default Collections (optional, comma-separated)
# Leave empty to query all collections
DEFAULT_COLLECTIONS=collection1,collection2
```

### 3. Start Backend API

Ensure the backend API is running:

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Run the Chatbot

```bash
cd chatbot
chainlit run rag_chatbot.py
```

The chatbot will open at: http://localhost:8001

## Usage

### Basic Queries

Simply ask questions naturally:

```
What is the company's remote work policy?
How do I submit a vacation request?
```

### Multi-Collection Queries

By default, the chatbot queries all collections. You can also select specific collections:

```
/use policies hr-docs
What is the vacation policy?
```

This will search only the "policies" and "hr-docs" collections.

### Commands

#### `/info`
Show current configuration

#### `/collections`
List all available collections

#### `/use <collection1> [collection2] ...`
Select specific collections to query

#### `/clear`
Clear selection (query all collections)

## Configuration

### Retrieval Settings

- `MAX_RESULTS_PER_COLLECTION`: Maximum results to retrieve per collection (default: 10)
- `MAX_TOTAL_RESULTS`: Maximum total results across all collections (default: 50)
- `MIN_SIMILARITY_SCORE`: Minimum similarity score (0-1) to include results (default: 0.3)
- `ENABLE_RERANKING`: Enable reranking by relevance (default: true)

### Performance Tuning

For large-scale deployments (100s of documents per collection):

1. **Increase per-collection results**: Set `MAX_RESULTS_PER_COLLECTION=20` or higher
2. **Increase total results**: Set `MAX_TOTAL_RESULTS=100` for comprehensive answers
3. **Adjust similarity threshold**: Lower `MIN_SIMILARITY_SCORE` to include more results
4. **Enable reranking**: Keeps `ENABLE_RERANKING=true` for better relevance

## API Integration

The module uses the backend API's search endpoint:

```
POST /collections/{collection_name}/search
Parameters:
  - query: str (search query text)
  - n_results: int (number of results to return)
```

The module automatically:
- Searches multiple collections in parallel
- Combines and reranks results
- Formats context for LLM

## Production Considerations

### Error Handling

- All API calls have proper error handling
- Graceful degradation when collections are unavailable
- Comprehensive logging for debugging

### Performance

- Parallel collection searches using `asyncio.gather`
- Efficient result processing
- Configurable result limits

### Scalability

- Supports 100s of documents per collection
- Handles multiple collections simultaneously
- Configurable result limits prevent memory issues

## Example: Programmatic Usage

```python
import asyncio
from rag_module import VectorDBClient, RAGEngine
from langchain_groq import ChatGroq

async def main():
    # Initialize client and engine
    async with VectorDBClient(api_base_url="http://localhost:8000") as client:
        llm = ChatGroq(
            groq_api_key="your_key",
            model_name="mixtral-8x7b-32768"
        )
        
        engine = RAGEngine(
            vector_db_client=client,
            llm=llm,
            max_results_per_collection=10,
            max_total_results=50
        )
        
        # Query specific collections
        response = await engine.query(
            query="What is the vacation policy?",
            collection_names=["hr-docs", "policies"]
        )
        
        print(f"Answer: {response.answer}")
        print(f"Sources: {len(response.sources)}")
        print(f"Collections searched: {response.collections_searched}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### "Error connecting to backend API"

- Verify backend API is running at the configured URL
- Check `BACKEND_API_URL` environment variable
- Ensure network connectivity

### "No collections found"

- Upload documents using the main UI
- Check backend API is accessible
- Verify collections exist in the database

### "No results found"

- Check if documents exist in the selected collections
- Lower `MIN_SIMILARITY_SCORE` to include more results
- Verify query is relevant to document content

## License

MIT License - Same as parent project

