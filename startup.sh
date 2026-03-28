#!/bin/bash
echo "=== STARTUP ==="
echo "PORT: ${PORT:-8000}"
echo "ENVIRONMENT: ${ENVIRONMENT:-not set}"
echo "DATABASE_URL: ${DATABASE_URL:-not set}"
echo "Python: $(python --version)"
echo "Working dir: $(pwd)"
echo "Files: $(ls)"
echo "=== STARTING UVICORN ==="
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info
