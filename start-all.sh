#!/bin/bash

# Start All Services Script for VectorDB Manager

echo "========================================="
echo "   VectorDB Manager - Starting All"
echo "========================================="
echo ""

# Get the directory where the script is located
DIR="$(cd "$(dirname "$0")" && pwd)"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $(jobs -p) 2>/dev/null
    exit
}

# Set up trap to cleanup on script exit
trap cleanup EXIT INT TERM

# Start backend in background
echo "Starting Backend..."
"$DIR/start-backend.sh" &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend in background
echo ""
echo "Starting Frontend..."
"$DIR/start-frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "========================================="
echo "   All services started!"
echo "========================================="
echo ""
echo "Backend API: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for all background processes
