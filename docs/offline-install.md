# Offline installation runbook / オフラインインストール手順

DocuEngine installs from a self-contained bundle. The client server never needs
internet access — not during install, not at runtime.

## Server requirements / サーバー要件

- Ubuntu 22.04+ (or any x86_64 Linux with Docker Engine 24+ and the compose plugin)
- NVIDIA GPU with 8 GB+ VRAM (RTX 3060/4060 class) + driver 535+ +
  `nvidia-container-toolkit` — **or** CPU-only (slower OCR, auto-detected)
- 16 GB RAM, 500 GB+ disk (documents + models + database)
- A fixed LAN IP reachable from scanner PCs and users' browsers

## Building the bundle (Sonasu side, internet-connected machine)

```bash
pip install huggingface_hub
python scripts/fetch_models.py          # downloads weights, fills manifest sha256s
bash docker/installer/bundle.sh 1.0.0   # → docuengine-bundle-1.0.0.tar.gz
```

## Installing on the client server / インストール

Copy the bundle over (USB drive is fine — that's the point), then:

```bash
tar xzf docuengine-bundle-1.0.0.tar.gz
cd docuengine-bundle-1.0.0
sudo ./install.sh
```

The installer verifies model checksums, generates secrets and a self-signed TLS
certificate, starts the stack, runs migrations, and prints the URL plus the
initial super-admin credentials (stored in `/opt/docuengine/compose/.env`).
**Change the super-admin password on first login.**

## First-time setup / 初期設定

1. Sonasu super admin logs in → registers the client company → issues the
   company-admin login.
2. Company admin logs in → registers users → registers the scanner device
   (the device token is shown **once** — paste it into the watcher app).
3. Install `DocuEngine Watcher` on the scanner PC (`watcher-app` NSIS
   installer), set server URL + device token + watch folder, press
   「保存して接続テスト」.
4. Scan a test document — it should appear in the web UI within seconds and
   finish OCR shortly after.

## Upgrades / アップグレード

```bash
cd docuengine-bundle-<new-version>
sudo ./upgrade.sh     # keeps database + documents, loads new images, migrates
```

## Notes

- TLS is self-signed by default; to trust it on client PCs, distribute
  `/opt/docuengine/tls/docuengine.crt` (the watcher app can pin it).
- CPU-only servers run PP-OCRv5 automatically; expect noticeably lower
  handwriting/table accuracy and slower batches.
