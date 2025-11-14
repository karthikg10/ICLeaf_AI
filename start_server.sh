#!/bin/bash
# Start the ICLeaF AI server

cd /Users/karthik/ICLeaf_AI/backend
source .venv/bin/activate

echo "Starting ICLeaF AI server on port 8000..."
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload



