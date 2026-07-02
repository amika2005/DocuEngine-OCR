#!/usr/bin/env bash
# Upgrade an existing DocuEngine install from a newer bundle. Volumes are preserved.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/docuengine}"
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ -f "$INSTALL_DIR/compose/.env" ] || { echo "No existing install at $INSTALL_DIR"; exit 1; }

echo "[upgrade] loading new images..."
docker load -i "$BUNDLE_DIR/images/docuengine-images.tar.zst" 2>/dev/null \
  || zstd -dc "$BUNDLE_DIR/images/docuengine-images.tar.zst" | docker load

echo "[upgrade] updating models + compose..."
cp -r "$BUNDLE_DIR/models/." "$INSTALL_DIR/models/"
cp "$BUNDLE_DIR/compose/docker-compose.yml" "$BUNDLE_DIR/compose/nginx.conf" "$INSTALL_DIR/compose/"

echo "[upgrade] restarting stack + migrating..."
(cd "$INSTALL_DIR/compose" && docker compose up -d)
(cd "$INSTALL_DIR/compose" && docker compose exec -T api alembic upgrade head)

echo "[upgrade] done."
