#!/usr/bin/env bash
# Launch the Kapruka fashion agent (chat UI at http://127.0.0.1:8000).
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/uvicorn main:app --reload "$@"
