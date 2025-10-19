#!/bin/bash

# VectorDB Chatbot Startup Script
# This script sets up the environment and starts the Chainlit chatbot

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Starting VectorDB Chatbot"
echo "============================================"
echo ""

# Find a compatible Python version (3.10, 3.11, or 3.12)
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        major=$(echo $version | cut -d'.' -f1)
        minor=$(echo $version | cut -d'.' -f2)
        
        # Check if version is 3.10, 3.11, or 3.12 (PyTorch compatible)
        if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_CMD=$cmd
            echo "✓ Found compatible Python: $cmd ($version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ ERROR: No compatible Python version found!"
    echo ""
    echo "PyTorch (required by sentence-transformers) doesn't support Python 3.13 yet."
    echo "Please install Python 3.10, 3.11, or 3.12:"
    echo ""
    echo "Using Homebrew:"
    echo "  brew install python@3.12"
    echo ""
    echo "Or download from:"
    echo "  https://www.python.org/downloads/"
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
echo "Installing dependencies (this may take a few minutes)..."
echo ""

# Install PyTorch first (CPU version)
echo "Installing PyTorch..."
pip install torch torchvision torchaudio || pip install torch

# Install other dependencies
echo "Installing other dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  No .env file found!"
    echo "Creating .env from .env.example..."
    
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ Created .env file"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  ⚠️  ACTION REQUIRED: Add API Key"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "1. Get a FREE API key from Groq:"
        echo "   👉 https://console.groq.com/keys"
        echo ""
        echo "2. Edit the .env file:"
        echo "   nano .env"
        echo ""
        echo "3. Add your key:"
        echo "   GROQ_API_KEY=gsk_your_key_here"
        echo ""
        echo "4. Save and run this script again"
        echo ""
        exit 1
    fi
fi

# Verify API key is set
source .env 2>/dev/null || true
if [ -z "$GROQ_API_KEY" ] && [ -z "$GOOGLE_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  ⚠️  No API Key Found in .env"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Get a FREE API key: https://console.groq.com/keys"
    echo ""
    echo "Then edit .env and add:"
    echo "  GROQ_API_KEY=gsk_your_key_here"
    echo ""
    read -p "Press Enter after adding your API key to continue..."
fi

echo ""
echo "============================================"
echo "  🚀 Starting Chatbot Server"
echo "============================================"
echo ""
echo "📍 Chatbot URL:"
echo "   http://localhost:8001"
echo ""
echo "💡 Tips:"
echo "   - Type '/help' for available commands"
echo "   - Type '/collections' to see collections"
echo "   - Press Ctrl+C to stop"
echo ""

# Start the chatbot
python -m chainlit run app.py --host 0.0.0.0 --port 8001
