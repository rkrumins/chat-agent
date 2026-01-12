#!/bin/bash

# Start Ingestion Service for VectorDB Manager
# Microservices architecture - delegates vector operations to vector-service

echo "Starting VectorDB Ingestion Service..."

# Navigate to ingestion-service directory
cd "$(dirname "$0")/ingestion-service"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Install shared_schemas from parent directory
pip install -q -e ../shared_schemas

# Configuration
export VECTOR_SERVICE_URL=${VECTOR_SERVICE_URL:-"http://localhost:8003"}
export LOG_LEVEL=${LOG_LEVEL:-"INFO"}

# Start the server
echo "Starting Ingestion Service..."
echo "  Service URL: http://localhost:8002"
echo "  Vector Service: $VECTOR_SERVICE_URL"
echo "  API Documentation: http://localhost:8002/docs"
echo ""

python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8002

