#!/bin/bash
# BLACK Launcher
# Usage: ./launch.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [ -f ".env" ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "⬡ Starting BLACK..."
python3 black.py
