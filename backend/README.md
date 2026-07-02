# DocuEngine backend

FastAPI API + Celery OCR workers. See the repository root README for the full picture.

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload
uv run pytest
```
