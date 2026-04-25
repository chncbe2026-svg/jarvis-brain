#!/usr/bin/env bash
# Render startup script

PORT="${PORT:-10000}"
echo "Starting Uvicorn on 0.0.0.0:$PORT"

exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
