#!/bin/bash

# Start Frontend Script for VectorDB Manager

echo "Starting VectorDB Manager Frontend..."

# Navigate to frontend directory
cd "$(dirname "$0")/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
fi

# Start the development server
echo "Starting React development server..."
echo "Application will be available at http://localhost:3000"
echo ""

npm start

