#!/bin/bash
# start.sh — Launch the Still Point Engine (FastAPI + React)
# Usage: ./start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Still Point Engine..."
echo ""

# Start FastAPI backend
echo "▶ Starting FastAPI backend on http://127.0.0.1:8000"
./stillpoint_env/bin/python server.py &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 2

# Start React frontend
echo "▶ Starting React frontend on http://localhost:5173"
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Still Point Engine running!"
echo "   → UI:  http://localhost:5173"
echo "   → API: http://127.0.0.1:8000"
echo ""
echo "Press Ctrl+C to stop both servers."

# Wait and clean up on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
