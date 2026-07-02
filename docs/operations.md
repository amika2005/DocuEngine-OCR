# Operations guide

## Daily health

```bash
cd /opt/docuengine/compose
docker compose ps                  # all services should be healthy/running
docker compose logs -f worker-gpu  # OCR throughput + errors
nvidia-smi                         # VRAM headroom (PaddleOCR-VL ≈ 4–5 GB)
```

Queue depth and per-company usage are visible to admins in the web UI
(`/company/usage`, super-admin `/admin/stats`).

## Backup / restore

```bash
sudo ./backup.sh /path/to/backups   # pg_dump + /data volume tar
```

Restore = fresh install, then `psql < docuengine-db-*.sql` into the postgres
container and untar the data archive into the `docuengine-data` volume.
Model adapters live under `/data/models/` and are included in the backup.

## Model versions: activate / rollback

- Training runs and candidates appear under 学習 (Training) in the company-admin
  UI. A candidate only becomes active when a human clicks 適用 (Activate).
- **Rollback**: open the model list, click ロールバック on the previously retired
  version. Takes effect on the next OCR task — no restart needed.
- Artifacts are never deleted; every version stays on disk for audit/rollback.

## Common issues

| Symptom | Check |
|---|---|
| Documents stuck in 待機中 (queued) | `docker compose logs worker-gpu` — model load errors usually mean the models volume is missing or checksums were skipped |
| CUDA OOM in logs | page resolution cap (`OCR_DPI`, `OCR_MAX_LONG_EDGE` in `.env`); the pipeline auto-retries at lower resolution and marks only that page failed |
| Watcher shows 未接続 | device token revoked? server URL/TLS reachable from the scanner PC? (`curl -k https://<server>/api/v1/health`) |
| Uploads rejected 429 | queue backpressure — a big batch is draining; the watcher retries automatically |
| Training run status `error` | run detail's eval_report.error in the UI; GPU busy or trainer image missing the `lora` extra are the usual causes |

## Data retention

`companies.settings.retention_days` (default: unlimited) — the hourly
maintenance task can be extended to purge old originals; markdown results and
the audit trail are small and kept indefinitely.
