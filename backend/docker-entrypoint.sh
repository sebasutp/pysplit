#!/bin/sh
# Production API entrypoint.
#
# The schema is migrated before the first request so a fresh volume and a
# restored backup both start on the same Alembic revision. There is exactly one
# Uvicorn worker because SQLite has a single writer (plan §12).
set -eu

: "${DATABASE_URL:?DATABASE_URL must be set}"

# File-backed SQLite needs a writable parent. The image owns /data, but a
# bind-mounted empty directory may not; fail early with a clear message.
python - <<'PY'
import os
import sys
from pathlib import Path

url = os.environ.get("DATABASE_URL", "")
prefix = "sqlite:///"
if url.startswith(prefix) and ":memory:" not in url:
    path = Path(url[len(prefix) :])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        sys.exit(f"cannot create database directory {path.parent}: {exc}")
PY

echo "Applying database migrations..."
alembic upgrade head

echo "Starting pysplit API..."
# Proxy headers are deliberately not trusted by Uvicorn. The application
# honours X-Forwarded-* only when TRUST_FORWARDED_HEADERS=true, and the API is
# published only inside the Compose network behind nginx.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --no-access-log \
  --no-proxy-headers
