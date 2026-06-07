#!/bin/bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."

if [ -f .server.pid ]; then
    PID=$(cat .server.pid)
    echo "Stopping FireFrame server (PID: $PID)..."
    kill $PID
    rm -f .server.pid
    echo "Stopped."
else
    echo "Server does not appear to be running (no .server.pid found)."
    
    # Fallback to finding and killing uvicorn for this app
    PIDS=$(ps aux | grep "python3 -m uvicorn backend.main:app" | grep -v grep | awk '{print $2}')
    if [ ! -z "$PIDS" ]; then
        echo "Found running processes manually. Killing them..."
        for p in $PIDS; do
            kill $p
        done
        echo "Stopped."
    fi
fi
