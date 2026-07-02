#!/usr/bin/env bash
# DocuEngine one-command offline installer.
# Run from inside an extracted docuengine-bundle-vX.Y.Z/ directory on the client server.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/docuengine}"
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()  { echo -e "\033[1;32m[docuengine]\033[0m $*"; }
fail() { echo -e "\033[1;31m[docuengine] ERROR:\033[0m $*" >&2; exit 1; }

# --- 1. Prerequisites ---
command -v docker >/dev/null || fail "docker is not installed. Install Docker Engine first."
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed."

GPU_MODE=1
if ! command -v nvidia-smi >/dev/null || ! nvidia-smi >/dev/null 2>&1; then
  log "No NVIDIA GPU detected — installing in CPU-only mode (PP-OCRv5). OCR will be slower."
  GPU_MODE=0
elif ! docker info 2>/dev/null | grep -qi nvidia; then
  fail "GPU present but nvidia-container-toolkit is not configured for Docker."
fi

# --- 2. Load images ---
log "Loading Docker images (this can take a few minutes)..."
docker load -i "$BUNDLE_DIR/images/docuengine-images.tar.zst" 2>/dev/null \
  || zstd -dc "$BUNDLE_DIR/images/docuengine-images.tar.zst" | docker load

# --- 3. Verify + install model weights ---
log "Verifying model weights..."
mkdir -p "$INSTALL_DIR/models"
python3 - "$BUNDLE_DIR/models/manifest.json" "$BUNDLE_DIR/models" <<'PY'
import hashlib, json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
root = pathlib.Path(sys.argv[2])

def sha256_dir(path):  # must match scripts/fetch_models.py
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_file():
            digest.update(file.relative_to(path).as_posix().encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()

for entry in manifest["models"]:
    p = root / entry["path"]
    digest = sha256_dir(p) if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest == entry["sha256"], f"sha256 mismatch for {entry['path']}"
print("all model checksums OK")
PY
cp -r "$BUNDLE_DIR/models/." "$INSTALL_DIR/models/"

# --- 4. Generate config, secrets, TLS ---
mkdir -p "$INSTALL_DIR/compose" "$INSTALL_DIR/tls"
cp "$BUNDLE_DIR/compose/docker-compose.yml" "$BUNDLE_DIR/compose/nginx.conf" "$INSTALL_DIR/compose/"

if [ ! -f "$INSTALL_DIR/compose/.env" ]; then
  log "Generating secrets..."
  SUPERADMIN_PW="$(openssl rand -base64 15)"
  cat > "$INSTALL_DIR/compose/.env" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SUPERADMIN_EMAIL=admin@sonasu.co.jp
SUPERADMIN_PASSWORD=$SUPERADMIN_PW
MODELS_HOST_DIR=$INSTALL_DIR/models
TLS_DIR=$INSTALL_DIR/tls
OCR_ENGINE=$([ "$GPU_MODE" = 1 ] && echo paddleocr-vl || echo ppocrv5-cpu)
EOF
  chmod 600 "$INSTALL_DIR/compose/.env"
fi

if [ ! -f "$INSTALL_DIR/tls/docuengine.crt" ]; then
  log "Generating self-signed TLS certificate..."
  openssl req -x509 -newkey rsa:4096 -sha256 -days 3650 -nodes \
    -keyout "$INSTALL_DIR/tls/docuengine.key" \
    -out "$INSTALL_DIR/tls/docuengine.crt" \
    -subj "/CN=docuengine.local/O=Sonasu" >/dev/null 2>&1
fi

# --- 5. Start stack ---
log "Starting DocuEngine..."
COMPOSE_ARGS=""
[ "$GPU_MODE" = 0 ] && COMPOSE_ARGS="--profile cpu-only"
(cd "$INSTALL_DIR/compose" && docker compose $COMPOSE_ARGS up -d)

# --- 6. Migrate + seed ---
log "Running database migrations and seeding the super admin..."
(cd "$INSTALL_DIR/compose" && docker compose exec -T api alembic upgrade head)
(cd "$INSTALL_DIR/compose" && docker compose exec -T api python -m app.db.seed)

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"
log "-----------------------------------------------------------"
log "DocuEngine is installed."
log "  URL:            https://$HOST_IP/"
log "  Super admin:    see SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD in $INSTALL_DIR/compose/.env"
log "  (Change the password after first login.)"
log "-----------------------------------------------------------"
