#!/bin/bash

# Start Ingestion Service for VectorDB Manager

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

# Start the server
echo "Starting Ingestion Service..."
echo "Service will be available at http://localhost:8002"
echo "API Documentation: http://localhost:8002/docs"
echo ""

python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8002
