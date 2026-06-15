#!/usr/bin/env bash
# Run the full app locally: FastAPI backend (:8000) + Vite frontend (:5173).
# Open http://localhost:5173 once it's up. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "No .venv found. Run 'make setup' first." >&2
  exit 1
fi

# Launched via python -m uvicorn (not the console script) to avoid a stale
# shebang ever pointing at the wrong interpreter.
.venv/bin/python -m uvicorn app.backend.main:app --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM

echo "Backend  -> http://localhost:8000"
echo "Frontend -> http://localhost:5173  (open this one)"

( cd app/frontend && npm run dev -- --port 5173 --strictPort )
