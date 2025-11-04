#!/bin/bash

# Complete Setup Script for VectorDB Application
# Sets up backend, frontend, and chatbot with correct Python version

set -e

PROJECT_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_ROOT"

echo "============================================"
echo "  VectorDB Application - Complete Setup"
echo "============================================"
echo ""

# Check Python version
echo "Step 1: Checking Python version..."
echo "-------------------------------------------"

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        major=$(echo $version | cut -d'.' -f1)
        minor=$(echo $version | cut -d'.' -f2)
        
        if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_CMD=$cmd
            echo "✅ Found compatible Python: $cmd ($version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ ERROR: No compatible Python version (3.10-3.12) found!"
    echo ""
    echo "Please install Python 3.12:"
    echo "  brew install python@3.12"
    echo ""
    exit 1
fi

echo ""
echo "Step 2: Setting up Backend..."
echo "-------------------------------------------"

cd backend

# Create/recreate venv if needed
if [ -d "venv" ]; then
    VENV_PYTHON=$(venv/bin/python --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    CURRENT_PYTHON=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    
    if [ "$VENV_PYTHON" != "$CURRENT_PYTHON" ]; then
        echo "Recreating backend venv with Python $CURRENT_PYTHON..."
        rm -rf venv
        $PYTHON_CMD -m venv venv
    fi
else
    echo "Creating backend venv..."
    $PYTHON_CMD -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip > /dev/null
echo "Installing backend dependencies..."
pip install -r requirements.txt

echo "✅ Backend setup complete"
deactivate

cd "$PROJECT_ROOT"
echo ""
echo "Step 3: Setting up Chatbot..."
echo "-------------------------------------------"

cd chatbot

# Create/recreate venv if needed
if [ -d "venv" ]; then
    VENV_PYTHON=$(venv/bin/python --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    CURRENT_PYTHON=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    
    if [ "$VENV_PYTHON" != "$CURRENT_PYTHON" ]; then
        echo "Recreating chatbot venv with Python $CURRENT_PYTHON..."
        rm -rf venv
        $PYTHON_CMD -m venv venv
    fi
else
    echo "Creating chatbot venv..."
    $PYTHON_CMD -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip > /dev/null
echo "Installing chatbot dependencies..."
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✅ Created .env file"
        echo ""
        echo "⚠️  ACTION REQUIRED: Add your API key to chatbot/.env"
        echo "   Get a free key: https://console.groq.com/keys"
    fi
fi

echo "✅ Chatbot setup complete"
deactivate

cd "$PROJECT_ROOT"
echo ""
echo "Step 4: Setting up Frontend..."
echo "-------------------------------------------"

cd frontend

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
    echo "✅ Frontend setup complete"
else
    echo "✅ Frontend dependencies already installed"
fi

cd "$PROJECT_ROOT"

echo ""
echo "============================================"
echo "  ✅ Setup Complete!"
echo "============================================"
echo ""
echo "Python version: $($PYTHON_CMD --version)"
echo ""
echo "All services are ready to run!"
echo ""
echo "To start all services:"
echo "  ./start-all.sh"
echo ""
echo "Or start individually:"
echo "  Backend:  cd backend && ./start-backend.sh"
echo "  Frontend: cd frontend && npm start"
echo "  Chatbot:  cd chatbot && ./start-chatbot.sh"
echo ""
echo "⚠️  Don't forget to add your API key to chatbot/.env"
echo ""
echo "📚 The chatbot now uses the new RAG module with:"
echo "   - Multi-collection query support"
echo "   - Backend API integration (no direct DB access)"
echo "   - Production-ready retrieval for 100s of documents"
echo ""

