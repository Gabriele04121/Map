#!/usr/bin/env sh
# Start TravelOS (needs only Python 3.9+; no pip install).
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3 || command -v python) || { echo "Python 3 not found"; exit 1; }
[ -f .env ] || cp .env.example .env
exec "$PY" run.py
