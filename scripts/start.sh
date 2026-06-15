#!/bin/bash

# Ensure we are in the project root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# The app reads .env itself (via python-dotenv). start.sh only needs HOST and
# PORT for the port check and the uvicorn flags, so read just those two values.
# (Sourcing the whole file would choke on values with spaces, e.g. a Shortcut
# name like "FireFrame Weather".)
_env_value() { grep -E "^$1=" .env | tail -n 1 | cut -d '=' -f2- | cut -d '#' -f1 | tr -d ' "'; }
if [ -f .env ]; then
    HOST=$(_env_value HOST)
    PORT=$(_env_value PORT)
fi

HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8765}

source .venv/bin/activate

# Kill anything already on the port so re-running always works
EXISTING=$(lsof -ti tcp:$PORT 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo "Port $PORT in use — killing existing process(es): $EXISTING"
    kill $EXISTING 2>/dev/null
    sleep 0.5
fi

echo "Starting FireFrame on $HOST:$PORT ..."
echo "Press Ctrl+C to stop."

# Save PID for stop.sh, then wait so Ctrl+C kills it cleanly
python3 -m uvicorn backend.main:app --host $HOST --port $PORT --workers 1 &
PID=$!
echo $PID > .server.pid

wait $PID
rm -f .server.pid
