#!/bin/bash
# run.sh — local dev launcher (auto-reload, localhost only).
# For editing/testing; to host for the tablet use scripts/start.sh.
# Reach a remote dev box via: ssh -L 8765:127.0.0.1:8765 <dev-box>
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "No .venv found. Create it first:"
    echo "    python3 -m venv .venv"
    echo "    ./.venv/bin/python -m pip install -r requirements.txt"
    exit 1
fi

HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8765}

echo "Starting Desk Companion (dev mode, auto-reload) on http://$HOST:$PORT ..."
echo "Press Ctrl+C to stop."

exec ./.venv/bin/python -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload
