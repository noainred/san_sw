#!/usr/bin/env bash
# san_sw 개발/운영 실행 스크립트.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

HOST="${SANSW_HOST:-0.0.0.0}"
PORT="${SANSW_PORT:-8000}"

# venv 우선 사용
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "san_sw v$(cat VERSION) 시작 → http://${HOST}:${PORT}"
exec "$PY" -m uvicorn backend.app.main:app --host "$HOST" --port "$PORT" "$@"
