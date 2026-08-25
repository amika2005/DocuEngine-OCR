import hashlib
import uuid
from pathlib import Path

from app.config import get_settings


def company_dir(company_id: uuid.UUID) -> Path:
    return get_settings().data_dir / str(company_id)


def document_dir(company_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    return company_dir(company_id) / "documents" / str(document_id)


def original_path(company_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> Path:
    suffix = Path(filename).suffix.lower() or ".bin"
    return document_dir(company_id, document_id) / f"original{suffix}"


def page_image_path(company_id: uuid.UUID, document_id: uuid.UUID, page_number: int) -> Path:
    return document_dir(company_id, document_id) / "pages" / f"p{page_number}.png"


def document_markdown_path(company_id: uuid.UUID, document_id: uuid.UUID) -> Path:
    return document_dir(company_id, document_id) / "results" / "document.md"


def save_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_writable(path.parent)
    path.write_bytes(data)


def ensure_writable(path: Path) -> None:
    """Make dirs under DATA_DIR writable by API and Celery even if they run as
    different uids (VPS compose runs the API as root and workers as 10001)."""
    settings = get_settings()
    root = settings.data_dir.resolve()
    current = path.resolve()
    try:
        current.relative_to(root)
    except ValueError:
        return
    for candidate in (current, *current.parents):
        try:
            if candidate == root.parent or candidate == candidate.anchor:
                break
            candidate.chmod(0o777)
        except OSError:
            pass
        if candidate == root:
            break


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
