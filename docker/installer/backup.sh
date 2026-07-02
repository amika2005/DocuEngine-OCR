#!/usr/bin/env bash
# Backup DocuEngine: database dump + document/model data volume.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/docuengine}"
BACKUP_DIR="${1:-/opt/docuengine/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

echo "[backup] dumping database..."
(cd "$INSTALL_DIR/compose" && docker compose exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-docuengine}" "${POSTGRES_DB:-docuengine}") \
  | gzip > "$BACKUP_DIR/docuengine-db-$STAMP.sql.gz"

echo "[backup] archiving data volume..."
docker run --rm -v docuengine_docuengine-data:/data -v "$BACKUP_DIR":/backup alpine \
  tar -czf "/backup/docuengine-data-$STAMP.tar.gz" -C /data .

echo "[backup] done: $BACKUP_DIR/docuengine-{db,data}-$STAMP.*"
