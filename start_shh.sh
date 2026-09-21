#!/usr/bin/env bash
set -e

echo "=== SHH 1.0 - Smart Host Hub Launcher ==="
pip install -r requirements.txt --quiet
python3 -m shh start "$@"
