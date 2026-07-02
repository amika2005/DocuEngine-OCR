# DocuEngine

**DocuEngine** is a fully offline, on-premise OCR document processing system by **Sonasu**,
built for Japanese companies that require all document data to stay inside their own network.

Scanned invoices, tax reports, quotations, and letters (printed **and** handwritten Japanese,
mixed with English) are converted to clean **Markdown** — including tables — by a local
GPU-accelerated document-parsing model. Nothing ever leaves the client's server.

## How it works

```
Canon scanner → watch folder → DocuEngine Watcher (Electron desktop app)
                                        │  auto-upload (device token)
                                        ▼
                     DocuEngine server (Docker Compose, on-premise)
   nginx → React web UI  +  FastAPI  +  PostgreSQL  +  Redis  +  GPU OCR worker
                                        │
                     Markdown results, correction editor, batch progress
                                        │
              corrections → nightly LoRA fine-tuning (eval-gated, per-company)
```

- **OCR engine**: PaddleOCR-VL 0.9B (Apache-2.0) — layout analysis, tables → markdown,
  Japanese + English, handwriting. PP-OCRv5 CPU fallback profile.
- **Multi-tenant**: Sonasu super admin → client companies → company admins → users.
- **Correction flywheel**: users fix OCR output in the web editor; approved corrections
  fine-tune a per-company LoRA adapter on a nightly schedule, gated by CER/TEDS evaluation
  with one-click rollback.
- **Batch-safe**: 50–100 document scanner batches queue per-page on the GPU with live
  progress over SSE.

## Repository layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI API + Celery OCR workers |
| `frontend/` | React web UI (Japanese-first, English toggle) |
| `watcher-app/` | Electron scanner-folder watcher for client PCs |
| `trainer/` | Correction-driven fine-tuning + evaluation gate |
| `docker/` | Compose stack, Dockerfiles, offline installer scripts |
| `scripts/` | Demo seed + golden evaluation set |
| `docs/` | Architecture, offline install runbook, operations |

## Development quickstart

Prerequisites: Docker + Docker Compose, Node 20+, Python 3.11+, `uv`.

```bash
cp .env.example .env
make dev          # postgres + redis + api (hot reload) + frontend dev server
make test         # backend pytest + frontend build/typecheck
```

The API serves OpenAPI docs at `http://localhost:8000/docs`.
Default super admin credentials are seeded from `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` in `.env`.

## Offline install (client servers)

Client servers are air-gapped. Installation uses a self-contained bundle
(images + model weights + compose files) built by `docker/installer/bundle.sh`
and installed with a single command:

```bash
sudo ./install.sh
```

See `docs/offline-install.md` for the full runbook.
