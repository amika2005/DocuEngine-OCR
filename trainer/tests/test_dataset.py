import os
import tempfile
import uuid
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="docuengine-trainer-test-")
os.environ.update(
    {
        "DATABASE_URL_OVERRIDE": f"sqlite+pysqlite:///{_tmp}/test.db",
        "DATA_DIR": os.path.join(_tmp, "data"),
        "SECRET_KEY": "test-secret",
    }
)

import pytest

from app.config import get_settings

get_settings.cache_clear()

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker
from app.models import Company, Correction, CorrectionStatus, Document, OcrResult, Page
from trainer.dataset import build_dataset, load_jsonl

Base.metadata.create_all(get_engine())


@pytest.fixture(scope="module")
def db():
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture(scope="module")
def corrections(db):
    company = Company(name="データ株式会社", slug="dataset-co")
    db.add(company)
    db.flush()
    # 10 documents, one approved correction each; 1 draft that must be excluded.
    for index in range(10):
        document = Document(
            company_id=company.id,
            original_filename=f"doc{index}.pdf",
            content_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
            mime_type="application/pdf",
            byte_size=1,
            storage_path="/dev/null",
        )
        db.add(document)
        db.flush()
        page = Page(
            document_id=document.id,
            company_id=company.id,
            page_number=1,
            image_path=f"/data/p{index}.png",
        )
        db.add(page)
        db.flush()
        result = OcrResult(
            page_id=page.id, company_id=company.id, markdown=f"raw {index}",
            layout_json={}, engine="mock", is_current=True,
        )
        db.add(result)
        db.flush()
        db.add(
            Correction(
                company_id=company.id,
                page_id=page.id,
                ocr_result_id=result.id,
                original_markdown=f"raw {index}",
                corrected_markdown=f"fixed {index}",
                status=(
                    CorrectionStatus.approved.value if index < 9 else CorrectionStatus.draft.value
                ),
            )
        )
    db.commit()
    return company


def test_build_dataset_splits_and_filters(db, corrections, tmp_path):
    stats = build_dataset(db, corrections.id, tmp_path, holdout_fraction=0.2)

    assert stats.total_pairs == 9  # draft excluded
    assert stats.holdout_pairs >= 1
    assert stats.train_pairs + stats.holdout_pairs == stats.total_pairs

    train = load_jsonl(tmp_path / "train.jsonl")
    holdout = load_jsonl(tmp_path / "holdout.jsonl")
    assert len(train) == stats.train_pairs
    assert len(holdout) == stats.holdout_pairs
    assert all(record["corrected_markdown"].startswith("fixed") for record in train + holdout)
    # No leakage: a correction id appears in exactly one split.
    assert not {r["correction_id"] for r in train} & {r["correction_id"] for r in holdout}


def test_build_dataset_deterministic(db, corrections, tmp_path):
    first = build_dataset(db, corrections.id, tmp_path / "a", seed=7)
    second = build_dataset(db, corrections.id, tmp_path / "b", seed=7)
    assert load_jsonl(tmp_path / "a" / "holdout.jsonl") == load_jsonl(
        tmp_path / "b" / "holdout.jsonl"
    )
    assert first.holdout_pairs == second.holdout_pairs
