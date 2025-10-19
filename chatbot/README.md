# VectorDB Chatbot

A standalone RAG (Retrieval Augmented Generation) chatbot built with Chainlit and LangChain that queries documents stored in your VectorDB.

## Features

- 🤖 **Multiple LLM Support**: Groq, Google Gemini, or OpenAI
- 📚 **Multi-Collection**: Switch between different document collections
- 🔍 **Smart Retrieval**: Finds relevant documents using semantic search
- 💬 **Interactive UI**: Beautiful Chainlit interface
- 📖 **Source Citations**: Shows which documents were used to answer
- ⚡ **Fast & Efficient**: Optimized for quick responses

## Quick Start

### 1. Install Dependencies

```bash
cd chatbot
pip install -r requirements.txt
```

### 2. Set Up Environment

```bash
cp .env.example .env
nano .env  # Edit with your settings
```

**Required Configuration:**

```env
# Point to your VectorDB
CHROMA_DB_PATH=../backend/chroma_db

# Choose LLM provider
LLM_PROVIDER=groq  # or gemini, or openai

# Add your API key
GROQ_API_KEY=your_api_key_here
```

### 3. Run the Chatbot

```bash
chainlit run app.py
```

The chatbot will open at: http://localhost:8001

## LLM Provider Setup

### Option 1: Groq (Recommended - Fast & Free)

1. Get API key from: https://console.groq.com/keys
2. Set in `.env`:
   ```env
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key
   MODEL_NAME=mixtral-8x7b-32768
   ```

**Available Groq Models:**
- `mixtral-8x7b-32768` (Recommended)
- `llama2-70b-4096`
- `gemma-7b-it`

### Option 2: Google Gemini

1. Get API key from: https://makersuite.google.com/app/apikey
2. Set in `.env`:
   ```env
   LLM_PROVIDER=gemini
   GOOGLE_API_KEY=your_google_api_key
   MODEL_NAME=gemini-pro
   ```

### Option 3: OpenAI

1. Get API key from: https://platform.openai.com/api-keys
2. Set in `.env`:
   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=your_openai_api_key
   MODEL_NAME=gpt-3.5-turbo
   ```

## Usage

### Chat Commands

Once the chatbot is running, you can use these commands:

#### `/info`
Show current configuration
```
/info
```

#### `/collections`
List all available collections in VectorDB
```
/collections
```

#### `/switch <collection_name>`
Switch to a different collection
```
/switch my-policies
```

### Regular Questions

Just type your question naturally:

```
What is the company's remote work policy?

How do I submit a vacation request?

What are the security guidelines for handling customer data?
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CHROMA_DB_PATH` | Path to VectorDB | `../backend/chroma_db` |
| `DEFAULT_COLLECTION` | Collection to load on start | None (uses first available) |
| `LLM_PROVIDER` | LLM provider to use | `groq` |
| `MODEL_NAME` | Model name | Provider-specific |
| `TEMPERATURE` | Response creativity (0-1) | `0.7` |
| `MAX_TOKENS` | Maximum response length | `1024` |

### Advanced Configuration

**Retrieval Settings** (in `app.py`):
```python
retriever=vectorstore.as_retriever(
    search_kwargs={"k": 5}  # Number of documents to retrieve
)
```

**Prompt Template** (in `app.py`):
Customize the prompt in the `create_qa_chain` function to change how the chatbot responds.

## Architecture

```
User Question
     ↓
Chainlit Interface
     ↓
LangChain RetrievalQA Chain
     ↓
ChromaDB Vector Store
     ↓
Document Retrieval (Top K chunks)
     ↓
LLM (Groq/Gemini/OpenAI)
     ↓
Generated Answer + Sources
     ↓
Chainlit Response
```

## Examples

### Example 1: Basic Q&A

**User:** "What is the vacation policy?"

**Bot Response:**
```
Based on the company policy documents, employees receive:
- 15 days of paid vacation annually
- Vacation must be requested 2 weeks in advance
- Unused vacation days roll over up to 5 days

---
Sources:
1. Employee Handbook (v2)
   > "All full-time employees are entitled to 15 days..."

2. HR Policy 2025
   > "Vacation requests should be submitted through..."
```

### Example 2: Multi-Collection

```
You: /collections

Bot: 📚 Available Collections:
     - company-policies (45 items)
     - technical-docs (120 items)
     - hr-handbook (30 items)
     
     💡 Use /switch <collection_name> to switch

You: /switch technical-docs

Bot: ✅ Switched to collection: technical-docs

You: How do I deploy to production?

Bot: According to the deployment documentation...
```

## Troubleshooting

### "Error loading vector store"

**Problem:** Can't connect to ChromaDB

**Solutions:**
1. Check `CHROMA_DB_PATH` is correct
2. Ensure VectorDB has documents (run the main app first)
3. Verify the path exists and is accessible

### "API key not set"

**Problem:** Missing or invalid API key

**Solutions:**
1. Check `.env` file has the correct API key
2. Ensure you're using the right variable name:
   - Groq: `GROQ_API_KEY`
   - Gemini: `GOOGLE_API_KEY`
   - OpenAI: `OPENAI_API_KEY`
3. Restart the chatbot after setting keys

### "No documents found"

**Problem:** Collection is empty or doesn't exist

**Solutions:**
1. Upload documents using the main VectorDB Manager app
2. Check collection name is correct
3. Use `/collections` to see available collections

### Slow Responses

**Problem:** Chatbot takes too long to respond

**Solutions:**
1. Reduce `k` value in retriever (fewer documents)
2. Use a faster model (e.g., `gemma-7b-it` for Groq)
3. Reduce `MAX_TOKENS` in `.env`

## Development

### Project Structure

```
chatbot/
├── app.py              # Main Chainlit application
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .chainlit           # Chainlit configuration
└── README.md           # This file
```

### Extending the Chatbot

#### Add Custom Prompts

Edit `prompt_template` in `create_qa_chain()`:

```python
prompt_template = """You are a [custom role].

Context: {context}
Question: {question}

[Custom instructions]

Answer:"""
```

#### Add More LLM Providers

Add a new condition in `get_llm()`:

```python
elif provider == "anthropic":
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(...)
```

#### Modify Retrieval

Change search parameters:

```python
retriever=vectorstore.as_retriever(
    search_type="mmr",  # Maximum Marginal Relevance
    search_kwargs={
        "k": 10,
        "fetch_k": 20
    }
)
```

## API Keys Guide

### Free Tier Limits

| Provider | Free Tier | Rate Limit |
|----------|-----------|------------|
| Groq | ✅ Yes | 30 req/min |
| Gemini | ✅ Yes | 60 req/min |
| OpenAI | ❌ Paid | Varies by plan |

### Best for Free Use

**Recommended: Groq**
- Fast inference
- Generous free tier
- Good models (Mixtral, LLaMA)

## Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8001"]
```

Build and run:
```bash
docker build -t vectordb-chatbot .
docker run -p 8001:8001 --env-file .env vectordb-chatbot
```

### Environment Variables in Production

Use secrets management:
```bash
# Don't commit .env to git!
export GROQ_API_KEY="your-key"
chainlit run app.py
```

## Security Notes

1. **API Keys**: Never commit `.env` to version control
2. **Access Control**: Consider adding authentication
3. **Rate Limiting**: Implement rate limiting for public deployments
4. **Input Validation**: The app validates inputs, but review for your use case

## Support

- **LangChain Docs**: https://python.langchain.com/docs/get_started/introduction
- **Chainlit Docs**: https://docs.chainlit.io/
- **ChromaDB Docs**: https://docs.trychroma.com/

## License

MIT License - Same as parent project

