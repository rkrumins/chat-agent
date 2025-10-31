#!/bin/bash

# Python Version Checker for VectorDB Application
# Ensures compatible Python version (3.10, 3.11, or 3.12) for sentence-transformers

set -e

echo "============================================"
echo "  Python Version Compatibility Check"
echo "============================================"
echo ""

# Find compatible Python version
PYTHON_CMD=""
PYTHON_VERSION=""

for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v $cmd &> /dev/null; then
        version=$($cmd --version 2>&1 | cut -d' ' -f2)
        major=$(echo $version | cut -d'.' -f1)
        minor=$(echo $version | cut -d'.' -f2)
        
        # Check if version is 3.10, 3.11, or 3.12 (PyTorch/sentence-transformers compatible)
        if [ "$major" = "3" ] && [ "$minor" -ge 10 ] && [ "$minor" -le 12 ]; then
            PYTHON_CMD=$cmd
            PYTHON_VERSION=$version
            echo "✅ Found compatible Python: $cmd (version $version)"
            break
        elif [ "$major" = "3" ] && [ "$minor" -ge 13 ]; then
            echo "⚠️  Found Python $version but it's too new (not compatible with PyTorch yet)"
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo "❌ ERROR: No compatible Python version found!"
    echo ""
    echo "sentence-transformers requires Python 3.10, 3.11, or 3.12"
    echo "Python 3.13+ is not yet supported by PyTorch."
    echo ""
    echo "Please install a compatible version:"
    echo ""
    echo "Using Homebrew:"
    echo "  brew install python@3.12"
    echo ""
    echo "Or download from:"
    echo "  https://www.python.org/downloads/"
    echo ""
    exit 1
fi

echo ""
echo "✅ Python version check passed!"
echo "   Using: $PYTHON_CMD ($PYTHON_VERSION)"
echo ""
echo "This version is compatible with:"
echo "  - sentence-transformers ✓"
echo "  - PyTorch ✓"
echo "  - ChromaDB ✓"
echo "  - FastAPI ✓"
echo "  - Chainlit ✓"
echo ""

# Export for other scripts to use
export COMPATIBLE_PYTHON=$PYTHON_CMD
echo "Environment variable set: COMPATIBLE_PYTHON=$PYTHON_CMD"
echo ""

