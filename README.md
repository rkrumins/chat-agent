# VectorDB Manager + RAG Chatbot

A complete vector database management system with:
1. **VectorDB Manager**: Full-stack application for managing ChromaDB with React + Material UI and FastAPI
2. **RAG Chatbot**: Standalone Chainlit chatbot for querying your documents using LangChain

## Features

### Core Functionality
- **Collection Management**: Create, view, and delete vector database collections
- **Document Management**: Upload, edit, view, and delete documents with rich metadata
- **Async Processing**: Background document processing with real-time status updates
- **Multi-Collection Support**: Manage multiple knowledge bases in a single database
- **Search Capability**: Semantic search across document collections
- **Task Monitoring**: Track processing status of documents being uploaded

### User Interface
- Modern, responsive Material UI design
- Intuitive navigation with sidebar and routing
- Real-time status updates for async operations
- Document preview and metadata editing
- Tag-based organization
- Custom metadata support (JSON)

### Backend API
- FastAPI with async support
- ChromaDB integration for vector storage
- Document chunking with overlap
- RESTful API endpoints
- CORS enabled for frontend integration
- Comprehensive error handling

## Architecture

```
chat-agent/
├── backend/
│   ├── main.py              # FastAPI application with all endpoints
│   ├── requirements.txt     # Python dependencies
│   └── .env.example         # Environment configuration template
└── frontend/
    ├── src/
    │   ├── components/      # React components
    │   │   ├── AppBar.js
    │   │   ├── Sidebar.js
    │   │   ├── CollectionList.js
    │   │   ├── DocumentList.js
    │   │   └── TaskMonitor.js
    │   ├── services/
    │   │   └── api.js       # API client
    │   ├── App.js           # Main app component
    │   └── index.js         # Entry point
    ├── public/
    │   └── index.html
    └── package.json         # Node dependencies
```

## Installation

### Prerequisites
- Python 3.8+
- Node.js 16+
- npm or yarn

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file (optional, defaults work fine):
```bash
cp .env.example .env
```

5. Run the backend server:
```bash
python main.py
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file (optional):
```bash
cp .env.example .env
```

4. Start the development server:
```bash
npm start
```

The application will open at `http://localhost:3000`

## Usage

### Creating a Collection

1. Click the "New Collection" button on the home page
2. Enter a collection name and optional description
3. Click "Create"

### Adding Documents

1. Select a collection from the sidebar or home page
2. Click "Add Document"
3. Fill in the document details:
   - **Name**: Document identifier
   - **Purpose**: Description of the document's purpose
   - **Tags**: Comma-separated tags for organization
   - **Content**: The actual document text
   - **Custom Metadata**: Additional JSON metadata
4. Click "Create"

The document will be processed asynchronously, and you'll see the status in the task monitor.

### Editing Documents

1. Navigate to a collection's document list
2. Click the edit icon for the document you want to modify
3. Update the fields
4. Click "Update"

### Monitoring Tasks

1. Click "Tasks" in the sidebar
2. View all processing tasks with their status
3. The page auto-refreshes every 2 seconds

## API Endpoints

### Collections
- `GET /collections` - List all collections
- `POST /collections` - Create a new collection
- `DELETE /collections/{name}` - Delete a collection

### Documents
- `GET /collections/{name}/documents` - List documents in a collection
- `GET /collections/{name}/documents/{id}` - Get a specific document
- `POST /collections/{name}/documents` - Create a document
- `PUT /collections/{name}/documents/{id}` - Update a document
- `DELETE /collections/{name}/documents/{id}` - Delete a document
- `POST /collections/{name}/search` - Search documents

### Tasks
- `GET /tasks` - List all tasks
- `GET /tasks/{id}/status` - Get task status

### Health
- `GET /health` - Health check
- `GET /` - API information

## Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **ChromaDB**: Vector database for embeddings
- **Pydantic**: Data validation using Python type annotations
- **Uvicorn**: ASGI server

### Frontend
- **React**: UI library
- **Material UI**: Component library
- **React Router**: Navigation
- **Axios**: HTTP client

## Features in Detail

### Asynchronous Processing
Documents are processed in the background using FastAPI's background tasks. This includes:
- Text chunking with configurable overlap
- Embedding generation (via ChromaDB)
- Storage in the vector database
- Status tracking through task IDs

### Document Chunking
Documents are automatically split into chunks for better retrieval:
- Default chunk size: 500 characters
- Overlap: 50 characters
- Chunks are linked to parent documents

### Metadata Management
Each document supports rich metadata:
- **Name**: Human-readable identifier
- **Purpose**: Document description
- **Tags**: Multiple tags for categorization
- **Custom Metadata**: Arbitrary JSON data
- **Timestamps**: Created and updated timestamps

### Search
The search endpoint uses ChromaDB's similarity search to find relevant documents based on semantic meaning.

## Development

### Backend Development

To run the backend in development mode with auto-reload:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development

The React development server includes hot reloading by default:
```bash
npm start
```

### API Documentation

FastAPI provides automatic interactive API documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

### Backend Environment Variables
- `CHROMA_DB_PATH`: Path to ChromaDB storage (default: `./chroma_db`)
- `API_HOST`: API host (default: `0.0.0.0`)
- `API_PORT`: API port (default: `8000`)
- `CORS_ORIGINS`: Allowed CORS origins (default: `http://localhost:3000`)

### Frontend Environment Variables
- `REACT_APP_API_URL`: Backend API URL (default: `http://localhost:8000`)

## Troubleshooting

### Backend Issues

**ChromaDB not initializing:**
- Ensure the `chroma_db` directory is writable
- Check Python version (3.8+ required)

**CORS errors:**
- Verify the frontend URL is in the CORS origins list
- Check that the backend is running on the correct port

### Frontend Issues

**Cannot connect to API:**
- Verify the backend is running
- Check the `REACT_APP_API_URL` in `.env`
- Look for CORS errors in the browser console

**Components not rendering:**
- Clear browser cache
- Check browser console for errors
- Verify all dependencies are installed

---

## 🤖 RAG Chatbot (NEW!)

A standalone chatbot application that lets you chat with your documents!

### Features
- 💬 Natural language Q&A with your documents
- 🔍 Automatic semantic search and retrieval
- 🤖 Multiple LLM support: **Groq**, **Google Gemini**, **OpenAI**
- 📚 Multi-collection support
- 🎨 Beautiful Chainlit interface
- 📖 Source citations with every answer
- ⚡ Fast responses with Groq (free tier!)

### Quick Start

```bash
# 1. Install dependencies
cd chatbot
pip install -r requirements.txt

# 2. Configure (add your API key)
cp .env.example .env
nano .env  # Add GROQ_API_KEY or other provider

# 3. Run!
chainlit run app.py
# Or: ./start-chatbot.sh
```

Opens at: **http://localhost:8001**

### Get API Keys (Free Options)

- **Groq** (Recommended): https://console.groq.com/keys
- **Google Gemini**: https://makersuite.google.com/app/apikey
- **OpenAI**: https://platform.openai.com/api-keys (paid)

### Example Usage

```
You: What is the vacation policy?

Bot: Based on the Employee Handbook, employees receive 15 days 
     of paid vacation annually. Requests must be submitted 2 
     weeks in advance...

     📚 Sources:
     1. Employee Handbook (v2)
        > "All full-time employees are entitled to..."
```

### Commands

- `/info` - Show configuration
- `/collections` - List available collections
- `/switch <name>` - Switch to different collection

**📖 Full Documentation:** See [CHATBOT_GUIDE.md](CHATBOT_GUIDE.md) and [chatbot/README.md](chatbot/README.md)

---

## Future Enhancements

Possible improvements for the application:
- ~~File upload support (PDF, DOCX, etc.)~~ ✅ **DONE!**
- ~~Document versioning~~ ✅ **DONE!**
- ~~RAG Chatbot~~ ✅ **DONE!**
- Batch document operations
- Advanced search filters
- User authentication
- Export/import functionality
- Analytics dashboard
- Embedding model configuration
- Custom chunking strategies
- WebSocket for real-time updates
- Chatbot conversation history
- Multi-document comparison

## Contributing

This is a template project. Feel free to fork and modify for your needs.

## License

MIT License - feel free to use this project for any purpose.

## Support

For issues and questions, please refer to the FastAPI and ChromaDB documentation:
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Material UI Documentation](https://mui.com/)
