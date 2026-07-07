# DocuEngine — Windows テスト環境セットアップ / Test Setup Guide

Run the full DocuEngine OCR system on a Windows PC to test whether that
machine's specs are adequate. Works with **or without** a GPU (auto-detected).

---

## 0. Check the PC specs first / まずPCスペックを確認

Open **PowerShell** and run this one line — it prints the OS, CPU, RAM and GPU:

```powershell
"OS: $((Get-CimInstance Win32_OperatingSystem).Caption)"; "CPU: $((Get-CimInstance Win32_Processor).Name) ($((Get-CimInstance Win32_Processor).NumberOfLogicalProcessors) threads)"; "RAM: $([math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)) GB"; Get-CimInstance Win32_VideoController | ForEach-Object { "GPU: $($_.Name) ($([math]::Round($_.AdapterRAM/1GB)) GB)" }
```

### What the numbers should be

| Spec | Minimum | Recommended | Effect on the system |
|---|---|---|---|
| OS | Windows 10 (64-bit) | Windows 11 | — |
| CPU | 4 cores | 8+ cores | Rasterization, matching, exports |
| RAM | 8 GB | 16 GB | OCR model + Postgres + workers |
| GPU | none (CPU mode) | any DirectX-12 GPU, 4 GB+ VRAM | **OCR speed — see below** |
| Disk free | 10 GB | 20 GB+ | Docker + models + documents |

### Expected OCR speed per page (measured, PP-OCRv6 "medium")

| Configuration | Per page | Single invoice, end-to-end |
|---|---|---|
| **GPU** (any DX12 GPU, DirectML) | ~1.5 s | ~6–9 s |
| CPU, `medium` model | ~40–47 s | ~50–60 s |
| CPU, `small` model | ~4 s | ~10 s |

> **Rule of thumb:** if the PC has *any* dedicated GPU (NVIDIA/AMD/Intel Arc),
> you get near-cloud speed. No GPU → use the `small` model (still under the
> 2-minute target). A DirectX-12 GPU is checked automatically; no CUDA needed.

---

## 1. Install the prerequisites (one-time) / 前提ソフト

Install these (all free). Reboot after Docker Desktop.

| Tool | Where | Check in PowerShell |
|---|---|---|
| Docker Desktop | https://www.docker.com/products/docker-desktop/ | `docker compose version` |
| Git | https://git-scm.com/download/win | `git --version` |
| Python 3.11+ | https://www.python.org/downloads/ (tick "Add to PATH") | `python --version` |
| uv | `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` | `uv --version` |
| Node.js 20+ | https://nodejs.org/ (LTS) | `node --version` |

---

## 2. Get the code / コード取得

Either `git clone`, or copy the whole `DocuEngine-OCR` folder via USB.

```powershell
git clone https://github.com/amika2005/DocuEngine-OCR.git
cd DocuEngine-OCR
git checkout claude/docuengine-offline-ocr-4rg15i
```

---

## 3. Start the database (Docker) / データベース起動

Make sure **Docker Desktop is running**, then:

```powershell
docker compose -f docker/docker-compose.dev.yml up -d
```

This starts PostgreSQL + Redis. Check: `docker ps` should show two containers.

---

## 4. Backend setup / バックエンド

```powershell
cd backend
copy ..\.env.example .env          # if backend\.env doesn't exist yet
uv sync --extra ocr                # installs the OCR stack (rapidocr, onnxruntime, etc.)
```

### If the PC HAS a GPU — enable DirectML acceleration

```powershell
uv pip uninstall onnxruntime
uv pip install onnxruntime-directml
```

Then edit **`backend\.env`** and set:

```
OCR_ENGINE=rapidocr
OCR_MODEL_SIZE=medium
OCR_USE_GPU=true
```

### If the PC has NO GPU — use the fast model

Edit **`backend\.env`**:

```
OCR_ENGINE=rapidocr
OCR_MODEL_SIZE=small
OCR_USE_GPU=false
```

### Create tables + demo accounts

```powershell
uv run alembic upgrade head
uv run python -m app.db.seed
uv run python ..\scripts\seed_demo.py
```

### Start the API (leave this window open) — terminal 1

```powershell
uv run uvicorn app.main:app --port 8000
```

Check: open http://localhost:8000/api/v1/health → should show `{"status":"ok"}`.

---

## 5. Start the OCR worker (leave open) — terminal 2 / OCRワーカー

```powershell
cd backend
uv run celery -A app.tasks.celery_app worker --pool=solo -l info -Q cpu,ocr_gpu
```

> **Important:** the `-Q cpu,ocr_gpu` part is required — without it, scanned
> documents get stuck on "処理中" forever. **Run only ONE worker** — two workers
> fight over the GPU and make OCR ~5× slower.

The **first** document after starting the worker is slow (~15–20 s) because the
GPU compiles shaders once; every document after that is fast.

**Models:** the first OCR run downloads the PP-OCRv6 models (~140 MB, needs
internet once) into `backend\models\ppocr\`. For a fully offline machine, copy
that `models` folder from a machine that already has it.

---

## 6. Frontend (leave open) — terminal 3 / フロントエンド

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in Chrome or Edge.

---

## 7. Log in and test / ログインしてテスト

| Role | Email | Password |
|---|---|---|
| User | `user@demo.jp` | `demo-user-pw` |
| Company admin | `admin@demo.jp` | `demo-admin-pw` |
| Super admin | `admin@sonasu.co.jp` | `change-me-on-first-login` |

**Speed test:** log in as the user → スキャン → drag a Japanese invoice (PDF or
photo) → time how long until the result appears. Compare against the table in
section 0 to judge whether the machine is fast enough.

Also try: the result page (bounding boxes, Fields tab if a template is set,
inline QR codes), 修正する (edit), Download → PDF / Excel.

---

## 8. Daily restart order / 毎回の起動順序

After the one-time setup, to run it again just open three PowerShell windows:

1. `docker compose -f docker/docker-compose.dev.yml up -d` (once; stays running)
2. **backend:** `cd backend` → `uv run uvicorn app.main:app --port 8000`
3. **worker:** `cd backend` → `uv run celery -A app.tasks.celery_app worker --pool=solo -l info -Q cpu,ocr_gpu`
4. **frontend:** `cd frontend` → `npm run dev`

(On the dev machine there's a `start-worker.bat` that runs the worker with
auto-restart — copy it if you like.)

---

## 9. Troubleshooting / トラブルシューティング

| Problem | Fix |
|---|---|
| `docker: command not found` | Docker Desktop not installed / not running |
| API `connection refused` | Docker containers not up → step 3 |
| Documents stuck on 処理中 | Worker not running, or missing `-Q cpu,ocr_gpu` → step 5 |
| OCR very slow (~15 s+) every time | Two workers running — kill all, start one. Or first-doc shader compile (normal, only once) |
| `onnxruntime` GPU errors | Run the `onnxruntime-directml` swap in step 4; falls back to CPU automatically if GPU unavailable |
| Port 5432 / 6379 in use | Another Postgres/Redis running — stop it or edit `docker/docker-compose.dev.yml` ports |
| Login fails after re-seed | Clear browser localStorage and log in again |

---

## What to report back after the test

- The spec-check output from section 0 (CPU / RAM / GPU)
- OCR time per page (GPU or CPU, which model)
- Whether accuracy looked good on real client documents

That tells us whether this machine class is right for the client deployment.
