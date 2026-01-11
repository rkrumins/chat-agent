#!/bin/bash

# Start all services for the VectorDB application with Python version check

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "============================================"
echo "  Starting VectorDB Application"
echo "============================================"
echo ""

# Check Python version
echo "Checking Python version compatibility..."
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        major=$(echo $version | cut -d'.' -f1)
        minor=$(echo $version | cut -d'.' -f2)
        
        if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_CMD=$cmd
            echo "✅ Using Python: $cmd ($version)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ ERROR: No compatible Python version (3.10-3.12) found!"
    echo "Please run: ./setup-all.sh"
    exit 1
fi

echo ""

# Function to check if a port is in use
check_port() {
    lsof -ti:$1 > /dev/null 2>&1
}

# Start Backend
if check_port 8000; then
    echo "⚠️  Backend already running on port 8000"
else
    echo "Starting Backend Server..."
    cd "$SCRIPT_DIR/backend"
    
    if [ ! -d "venv" ]; then
        echo "❌ Backend not set up. Run: ./setup-all.sh"
        exit 1
    fi
    
    source venv/bin/activate
    $PYTHON_CMD -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    echo "✓ Backend started (PID: $BACKEND_PID)"
    deactivate
fi

# Start Ingestion Service
if check_port 8002; then
    echo "⚠️  Ingestion Service already running on port 8002"
else
    echo "Starting Ingestion Service..."
    cd "$SCRIPT_DIR/ingestion-service"
    
    if [ ! -d "venv" ]; then
        echo "Creating Ingestion Service virtual environment..."
        $PYTHON_CMD -m venv venv
        source venv/bin/activate
        pip install -q -r requirements.txt
    else
        source venv/bin/activate
    fi
    
    $PYTHON_CMD -m uvicorn main:app --reload --host 0.0.0.0 --port 8002 &
    INGESTION_PID=$!
    echo "✓ Ingestion Service started (PID: $INGESTION_PID)"
    deactivate
fi

# Start Frontend
if check_port 3000; then
    echo "⚠️  Frontend already running on port 3000"
else
    echo "Starting Frontend..."
    cd "$SCRIPT_DIR/frontend"
    
    if [ ! -d "node_modules" ]; then
        echo "❌ Frontend not set up. Run: ./setup-all.sh"
        exit 1
    fi
    
    npm start &
    FRONTEND_PID=$!
    echo "✓ Frontend started (PID: $FRONTEND_PID)"
fi


# Start Chatbot
if check_port 8001; then
    echo "⚠️  Chatbot already running on port 8001"
else
    echo "Starting Chatbot..."
    cd "$SCRIPT_DIR/chatbot"
    
    if [ ! -d "venv" ]; then
        echo "❌ Chatbot not set up. Run: ./setup-all.sh"
        exit 1
    fi
    
    source venv/bin/activate
    $PYTHON_CMD -m chainlit run rag_chatbot.py --host 0.0.0.0 --port 8001 &
    CHATBOT_PID=$!
    echo "✓ Chatbot started (PID: $CHATBOT_PID)"
    deactivate
fi

cd "$SCRIPT_DIR"

echo ""
echo "============================================"
echo "  ✅ All Services Started!"
echo "============================================"
echo ""
echo "Python version: $($PYTHON_CMD --version)"
echo ""
echo "Access the application:"
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Ingestion: http://localhost:8002 (Document Processing Microservice)"
echo "  Chatbot:   http://localhost:8001 (RAG Module with Multi-Collection Support)"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""


# Wait for user interrupt
wait
