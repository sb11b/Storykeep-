#!/bin/sh
set -e
PORT="${PORT:-8080}"
export PYTHONPATH="${PYTHONPATH:-/app}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --timeout-keep-alive 120
