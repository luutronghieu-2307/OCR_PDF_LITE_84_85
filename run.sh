#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "[INFO] Initializing virtual environment and installing dependencies..."
    if [ -f "$HOME/.local/bin/uv" ]; then
        "$HOME/.local/bin/uv" venv .venv --python 3.13
        source .venv/bin/activate
        "$HOME/.local/bin/uv" pip install -r requirements.txt
    elif command -v uv >/dev/null 2>&1; then
        uv venv .venv --python 3.13
        source .venv/bin/activate
        uv pip install -r requirements.txt
    else
        python3 -m venv .venv
        source .venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
    fi
else
    source .venv/bin/activate
fi

# Ensure libxcb-cursor compatibility for PyQt6
if [ -d "$SCRIPT_DIR/libs" ]; then
    export LD_LIBRARY_PATH="$SCRIPT_DIR/libs:${LD_LIBRARY_PATH:-}"
    PYQT6_LIB=$(find .venv -path "*/PyQt6/Qt6/lib" -type d 2>/dev/null | head -n 1)
    if [ -n "$PYQT6_LIB" ] && [ ! -f "$PYQT6_LIB/libxcb-cursor.so.0" ]; then
        cp "$SCRIPT_DIR"/libs/libxcb-cursor.so.0* "$PYQT6_LIB/" 2>/dev/null || true
    fi
fi

python3 src/main.py "$@"
