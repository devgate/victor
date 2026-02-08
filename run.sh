#!/bin/bash
# Victor Trading System - Run script
# Clears caches before running to avoid issues

cd "$(dirname "$0")"

# Clear Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

# Note: ~/.pykis contains KIS API tokens
# Only delete if you have token issues: rm -rf ~/.pykis

# Run with no bytecode writing
export PYTHONDONTWRITEBYTECODE=1

# Execute main.py with all arguments passed to this script
python3.11 main.py "$@"
