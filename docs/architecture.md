# DocuEngine architecture

## System overview

```
Canon scanner → watch folder → DocuEngine Watcher (Electron, on the scanner PC)
                                     │ HTTPS + X-Device-Token, idempotent uploads
                                     ▼
┌───────────────────── client server (Docker Compose) ──────────────────────┐
│ frontend   nginx: React SPA + /api reverse proxy + TLS                    │
│ api        FastAPI (auth, tenancy, documents, corrections, ingest, SSE)   │
│ postgres   PostgreSQL 16 — all metadata, tenant-scoped by company_id      │
│ redis      Celery broker/backend + progress event pub/sub                 │
│ worker-cpu Celery `cpu` queue: PDF rasterize, markdown assembly, cleanup  │
│ worker-gpu Celery `ocr_gpu` queue: concurrency=1, model resident on GPU   │
│ beat       schedules nightly training window + housekeeping               │
│ trainer    Celery `training` queue: LoRA fine-tune + eval gate (optional) │
│ /data      originals, page PNGs, markdown results, datasets, adapters     │
└────────────────────────────────────────────────────────────────────────────┘
```

Everything runs on the client's premises. No runtime network egress: model
weights are mounted read-only from `/opt/docuengine/models`, and offline env
flags (`HF_HUB_OFFLINE`, `PADDLE_PDX_MODEL_SOURCE=local`) are set in compose.

## OCR pipeline

One document flows through three Celery tasks (`backend/app/tasks/ocr_tasks.py`):

1. `rasterize_document` (cpu) — PyMuPDF renders each page at 200 DPI (long edge
   capped at 2600 px to bound VRAM), creates `pages` rows, fans out per-page
   OCR tasks with a chord callback.
2. `ocr_page` (ocr_gpu, prefetch=1, acks_late) — the engine parses layout +
   text into regions; `assemble.py` orders regions (vertical Japanese text is
   read right-to-left), converts tables to GFM, and stores an `ocr_results`
   row. Failures mark only that page failed.
3. `assemble_document` (cpu) — concatenates page markdown, writes
   `document.md`, updates batch counters, emits SSE events.

Per-page granularity is what makes 100-document scanner batches safe on one
GPU: FIFO drain, fine-grained progress, one crash loses at most one page.

### Engine seam

`backend/app/ocr/engine.py` defines `OcrEngine.parse_page(image) -> PageResult`.
Implementations:

| Engine | File | Use |
|---|---|---|
| PaddleOCR-VL 0.9B | `paddle_vl.py` | primary (GPU): layout + JA/EN + handwriting + tables |
| PP-OCRv5 | `ppocrv5.py` | CPU-only installs / degraded mode |
| Mock | `mock.py` | tests, CI, model-less development |

Selected via `OCR_ENGINE`. Swapping in another model (e.g. a future VLM) means
implementing one class.

## Multi-tenancy

Roles: `super_admin` (Sonasu staff, `company_id IS NULL`) → `company_admin` →
`user`. Every tenant table carries `company_id`; every route resolves the
subject from the JWT/device token and filters by it — cross-tenant access is a
404, verified by `backend/tests/test_tenancy.py`. Watcher devices authenticate
with a hashed long-lived token (`devices.token_hash`, raw value shown once).

## Correction → fine-tuning loop

1. Users fix page markdown in the CorrectionEditor; drafts autosave.
2. Submitted corrections enter the company admin's review queue (skippable per
   company via `settings.require_correction_approval`).
3. Nightly (02:00 JST) `maybe_start_training` fires per tenant once ≥200
   approved corrections accumulate → `trainer.run_training`.
4. The trainer pauses `ocr_gpu` consumption (it owns the GPU; OCR jobs queue
   up), builds a train/holdout dataset split by document, fine-tunes a
   per-company adapter, and evaluates baseline vs candidate.
5. Gate (`trainer/trainer/evaluate.py`): holdout CER must improve ≥2% relative
   AND the fixed golden set must not regress. Pass → `candidate` model version;
   a human clicks activate in the UI. Rollback = one click; artifacts kept.

## Progress events

Workers publish JSON events to one Redis channel
(`backend/app/events/publisher.py`); the API's `/api/v1/events` SSE endpoint
filters by the subscriber's company. Topics: `document.{id}.progress`,
`document.{id}.status`, `batch.{id}.progress`, `training.*`.

## Key files

- `backend/app/tasks/ocr_tasks.py` — pipeline orchestration
- `backend/app/ocr/assemble.py` — reading order + tables → markdown
- `backend/app/ocr/metrics.py` — CER (NFKC), table-cell F1 (shared with trainer)
- `trainer/trainer/celery_app.py` — training run lifecycle
- `docker/docker-compose.yml` — service topology
- `docker/installer/` — offline bundle + install/upgrade/backup
