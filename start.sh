#!/usr/bin/env bash
# One command to set up (first time only) and start Agent Studio at http://127.0.0.1:8765
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating Python virtualenv..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages..."
  (cd frontend && npm install --silent)
fi

# Rebuild the UI if any source file is newer than the last build.
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html)" ]; then
  echo "Building the UI..."
  (cd frontend && npm run build --silent)
fi

command -v claude >/dev/null || { echo "The 'claude' command was not found. Install Claude Code first."; exit 1; }

echo "Agent Studio: http://127.0.0.1:8765"
cd backend
# Bound to 127.0.0.1 only: agents run commands on this machine, so never expose this to a network.
exec ../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
