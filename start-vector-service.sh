#!/bin/bash

# Start Vector Service
cd "$(dirname "$0")"

cd vector-service

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Install shared_schemas from parent directory
pip install -q -e ../shared_schemas

# Configuration
export VECTOR_BACKEND=${VECTOR_BACKEND:-"chromadb"}
export CHROMA_DB_PATH=${CHROMA_DB_PATH:-"./chroma_db"}
export EMBEDDING_PROVIDER=${EMBEDDING_PROVIDER:-"sentence-transformers"}
export LOG_LEVEL=${LOG_LEVEL:-"INFO"}

echo "Starting Vector Service..."
echo "  Backend: $VECTOR_BACKEND"
echo "  ChromaDB Path: $CHROMA_DB_PATH"
echo "  Embedding Provider: $EMBEDDING_PROVIDER"
echo ""

# Run the service
python -m uvicorn main:app --host 0.0.0.0 --port 8003 --reload
