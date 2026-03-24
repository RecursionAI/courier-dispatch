#!/usr/bin/env bash
set -euo pipefail

# Build a standalone dispatch binary using PyInstaller

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Building dispatch binary..."

pyinstaller \
    --name dispatch \
    --onefile \
    --clean \
    --collect-all mcp \
    --hidden-import uvicorn \
    --hidden-import starlette \
    src/courier_dispatch/server.py

echo ""
echo "Build complete: dist/dispatch"
echo "Run with: ./dist/dispatch /path/to/project"
