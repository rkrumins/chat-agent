#!/bin/bash

# Start Backend Script for VectorDB Manager

echo "Starting VectorDB Manager Backend..."

# Navigate to backend directory
cd "$(dirname "$0")/backend"

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

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
fi

# Start the server
echo "Starting FastAPI server..."
echo "API will be available at http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""

python3 main.py

