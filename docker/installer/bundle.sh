#!/usr/bin/env bash
# Builds the offline install bundle (run on a machine WITH internet, e.g. CI).
# Output: docuengine-bundle-<version>.tar.gz
set -euo pipefail

VERSION="${1:?usage: bundle.sh <version>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="docuengine-bundle-$VERSION"
STAGE="$(mktemp -d)/$OUT"
mkdir -p "$STAGE"/{images,models,compose,docs}

echo "[bundle] building images..."
docker build -t "docuengine/backend:$VERSION"  -f "$REPO_ROOT/docker/api.Dockerfile" "$REPO_ROOT"
docker build -t "docuengine/frontend:$VERSION" -f "$REPO_ROOT/docker/frontend.Dockerfile" "$REPO_ROOT"
docker build -t "docuengine/trainer:$VERSION"  -f "$REPO_ROOT/docker/trainer.Dockerfile" "$REPO_ROOT"

echo "[bundle] saving images..."
docker save \
  "docuengine/backend:$VERSION" \
  "docuengine/frontend:$VERSION" \
  "docuengine/trainer:$VERSION" \
  postgres:16-alpine redis:7-alpine \
  | zstd -T0 -o "$STAGE/images/docuengine-images.tar.zst"

echo "[bundle] collecting model weights..."
# Model weights must be pre-downloaded into $REPO_ROOT/models by scripts/fetch_models.py
[ -f "$REPO_ROOT/models/manifest.json" ] || { echo "models/manifest.json missing — run scripts/fetch_models.py first"; exit 1; }
cp -r "$REPO_ROOT/models/." "$STAGE/models/"

echo "[bundle] compose + docs..."
sed "s/\${DOCUENGINE_VERSION:-latest}/$VERSION/g" "$REPO_ROOT/docker/docker-compose.yml" > "$STAGE/compose/docker-compose.yml"
cp "$REPO_ROOT/docker/nginx.conf" "$STAGE/compose/"
cp "$REPO_ROOT/docker/installer/install.sh" "$REPO_ROOT/docker/installer/upgrade.sh" "$REPO_ROOT/docker/installer/backup.sh" "$STAGE/"
cp "$REPO_ROOT/docs/offline-install.md" "$STAGE/docs/" 2>/dev/null || true
chmod +x "$STAGE"/*.sh

echo "[bundle] packing..."
tar -C "$(dirname "$STAGE")" -czf "$OUT.tar.gz" "$OUT"
echo "[bundle] done: $OUT.tar.gz"
