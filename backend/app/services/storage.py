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
    path.write_bytes(data)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
