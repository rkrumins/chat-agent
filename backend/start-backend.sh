#!/bin/bash

# Backend Server Startup Script with Python Version Check

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Starting VectorDB Backend Server"
echo "============================================"
echo ""

# Find a compatible Python version (3.10, 3.11, or 3.12)
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        major=$(echo $version | cut -d'.' -f1)
        minor=$(echo $version | cut -d'.' -f2)
        
        # Check if version is 3.10, 3.11, or 3.12
        if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_CMD=$cmd
            echo "✅ Found compatible Python: $cmd ($version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ ERROR: No compatible Python version found!"
    echo ""
    echo "sentence-transformers requires Python 3.10, 3.11, or 3.12"
    echo "Please install: brew install python@3.12"
    echo ""
    exit 1
fi

# Check if virtual environment exists or needs recreation
RECREATE_VENV=false
if [ -d "venv" ]; then
    # Check if venv uses the right Python version
    VENV_PYTHON=$(venv/bin/python --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    CURRENT_PYTHON=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    
    if [ "$VENV_PYTHON" != "$CURRENT_PYTHON" ]; then
        echo "⚠️  Virtual environment uses Python $VENV_PYTHON, but we need $CURRENT_PYTHON"
        echo "Recreating virtual environment..."
        rm -rf venv
        RECREATE_VENV=true
    fi
else
    RECREATE_VENV=true
fi

if [ "$RECREATE_VENV" = true ]; then
    echo "Creating virtual environment with $PYTHON_CMD..."
    $PYTHON_CMD -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "============================================"
echo "  🚀 Starting Backend Server"
echo "============================================"
echo ""
echo "📍 API will be available at:"
echo "   http://localhost:8000"
echo "   http://localhost:8000/docs (API docs)"
echo ""
echo "💡 Tips:"
echo "   - Backend must be running for UI and chatbot to work"
echo "   - Press Ctrl+C to stop"
echo ""

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000

