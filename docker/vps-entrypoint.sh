#!/bin/sh
# VPS / IP:port API entry: wait for this stack's Postgres, migrate, seed, serve.
set -eu
umask 000

echo "Waiting for DocuEngine database..."
python - <<'PY'
import os, sys, time
import psycopg

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
db = os.environ.get("POSTGRES_DB", "docuengine")
user = os.environ.get("POSTGRES_USER", "docuengine")
password = os.environ.get("POSTGRES_PASSWORD", "")
dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"

deadline = time.time() + 90
last = None
while time.time() < deadline:
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        print("database is ready")
        sys.exit(0)
    except Exception as exc:
        last = exc
        time.sleep(1)
print(f"database not ready: {last}", file=sys.stderr)
sys.exit(1)
PY

echo "Applying DocuEngine migrations (docuengine DB only)..."
alembic upgrade head

mkdir -p /data
chmod -R a+rwX /data || true

if [ "${RUN_SEED:-1}" = "1" ]; then
  echo "Seeding super admin..."
  python -m app.db.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
