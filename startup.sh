#!/bin/bash
set -e
echo "PORT=$PORT"
echo "Python=$(python --version)"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
