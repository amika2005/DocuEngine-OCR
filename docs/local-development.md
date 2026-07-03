# Local development & testing guide

Run the full DocuEngine stack on a laptop — no GPU needed. The `mock` OCR
engine produces realistic Japanese-invoice markdown so every flow (scan →
queue → result → correction → approval → dashboards) is testable end-to-end.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Git | any | `git --version` |
| Docker Desktop (or Engine+compose) | 24+ | `docker compose version` |
| Python | 3.11+ | `python3 --version` |
| uv | latest | `uv --version` (install: https://docs.astral.sh/uv/) |
| Node.js | 20+ | `node --version` |

> **Windows note**: everything works natively, but WSL2 (Ubuntu) is smoother.
> If running Celery natively on Windows, add `--pool=solo` to the worker command.

## 1. Clone

```bash
git clone https://github.com/amika2005/DocuEngine-OCR.git
cd DocuEngine-OCR
git checkout claude/docuengine-offline-ocr-4rg15i
```

## 2. Infra (PostgreSQL + Redis)

```bash
docker compose -f docker/docker-compose.dev.yml up -d
```

## 3. Backend — terminal 1

```bash
cp .env.example backend/.env        # defaults already match the dev compose infra
cd backend
uv sync --extra dev                 # install dependencies
uv run alembic upgrade head         # create tables
uv run python -m app.db.seed        # Sonasu super admin + base model registry
uv run python ../scripts/seed_demo.py   # demo company + demo users
uv run uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## 4. OCR worker — terminal 2

```bash
cd backend
uv run celery -A app.tasks.celery_app worker -Q cpu,ocr_gpu -c 2 --loglevel=info
# Windows (native): append --pool=solo
```

`OCR_ENGINE=mock` (the default in `.env.example`) means no model download —
every page comes back as a sample 請求書 with a markdown table.

## 5. Frontend — terminal 3

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** (API calls proxy to :8000 automatically).

## 6. Login accounts (from the seeds)

| Role | Email | Password |
|---|---|---|
| Super admin (Sonasu) | `admin@sonasu.co.jp` | `change-me-on-first-login` (from backend/.env) |
| Company admin (demo) | `admin@demo.jp` | `demo-admin-pw` |
| User (demo) | `user@demo.jp` | `demo-user-pw` |

## 7. What to test

1. **User flow** — login as `user@demo.jp` → dashboard tiles → スキャン page →
   drag-drop any PDF/PNG → watch live progress → open the document → markdown
   beside the page image → 修正する → edit in CodeMirror → 修正を送信.
2. **Admin flow** — login as `admin@demo.jp` (second browser/incognito) →
   dashboard shows the pending correction → 修正 page → 承認 → watch the user's
   dashboard update in real time. Add a user, register a device (token shows
   once), check ユーザー管理/スキャナー端末 update live.
3. **Super admin flow** — login as the Sonasu account → global dashboard →
   register a company → issue its admin login → per-company table updates.
4. **Duplicate handling** — upload the same file twice → 重複 (409) as designed.

## 8. Watcher app (optional)

```bash
cd watcher-app
npm install        # downloads the Electron binary
npm start
```

Set server URL `http://localhost:8000`, paste a device token created in the
admin UI, pick a watch folder, then drop PDFs into that folder — they upload
and OCR automatically (batch grouping within 60s).

## 9. Automated tests

```bash
make test          # backend pytest + frontend build
cd trainer && uv sync --extra dev && uv run pytest   # trainer suite
```

## 10. Real OCR on a laptop (optional, CPU — slow)

```bash
cd backend
uv sync --extra ocr                      # installs paddleocr (+ paddlepaddle CPU)
# in backend/.env:  OCR_ENGINE=ppocrv5-cpu
```

First run downloads PP-OCRv5 models (internet needed once). Expect ~10–60s per
page on laptop CPU — fine for correctness checks, not throughput. The full
PaddleOCR-VL engine is worth testing only on a CUDA GPU machine.

## Troubleshooting

| Problem | Fix |
|---|---|
| `connection refused` on API start | infra not up: `docker compose -f docker/docker-compose.dev.yml up -d` |
| Documents stuck 待機中 | worker terminal not running / crashed — restart step 4 |
| Celery errors on Windows | add `--pool=solo`, or use WSL2 |
| Port 5432/6379 already in use | stop local postgres/redis or edit dev compose ports |
| Login fails after reseed | tokens cached — clear browser localStorage and re-login |
