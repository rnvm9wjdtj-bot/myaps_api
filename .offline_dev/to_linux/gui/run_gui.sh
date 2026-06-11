#!/bin/bash
# MyAPS API - 离线迁移工具启动脚本 (Linux/macOS)
cd "$(dirname "$0")/.."
echo "Starting MyAPS API Offline Migration Tool (Linux)..."

# macOS specific: suppress IMK CFRunLoop warning
if [[ "$(uname)" == "Darwin" ]]; then
    # Try pythonw first (better for GUI apps on macOS)
    if command -v pythonw3 &> /dev/null; then
        pythonw3 gui/main.py 2>/dev/null
    else
        # Fallback: suppress stderr on macOS
        python3 gui/main.py 2>/dev/null
    fi
else
    python3 gui/main.py
fi