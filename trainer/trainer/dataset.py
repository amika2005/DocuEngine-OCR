"""Builds a fine-tuning dataset from approved corrections: JSONL of
(page image path, original markdown, corrected markdown) with a stratified
train/holdout split by document, so a multi-page document never leaks across
the split."""

import json
import random
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Correction, CorrectionStatus, Page


@dataclass
class DatasetStats:
    total_pairs: int
    train_pairs: int
    holdout_pairs: int
    correction_ids: list[str]

    def as_dict(self) -> dict:
        return {
            "total_pairs": self.total_pairs,
            "train_pairs": self.train_pairs,
            "holdout_pairs": self.holdout_pairs,
        }


def build_dataset(
    db: Session,
    company_id: uuid.UUID,
    output_dir: Path,
    holdout_fraction: float = 0.1,
    seed: int = 42,
) -> DatasetStats:
    corrections = db.execute(
        select(Correction, Page)
        .join(Page, Correction.page_id == Page.id)
        .where(
            Correction.company_id == company_id,
            Correction.status == CorrectionStatus.approved.value,
        )
        .order_by(Correction.created_at)
    ).all()

    # Group by document so pages of one document stay on one side of the split.
    by_document: dict[uuid.UUID, list[tuple[Correction, Page]]] = {}
    for correction, page in corrections:
        by_document.setdefault(page.document_id, []).append((correction, page))

    documents = list(by_document.keys())
    random.Random(seed).shuffle(documents)
    holdout_count = max(1, int(len(documents) * holdout_fraction)) if documents else 0
    holdout_documents = set(documents[:holdout_count])

    output_dir.mkdir(parents=True, exist_ok=True)
    stats = DatasetStats(0, 0, 0, [])
    with (
        open(output_dir / "train.jsonl", "w", encoding="utf-8") as train_file,
        open(output_dir / "holdout.jsonl", "w", encoding="utf-8") as holdout_file,
    ):
        for document_id, pairs in by_document.items():
            target = holdout_file if document_id in holdout_documents else train_file
            for correction, page in pairs:
                record = {
                    "image": page.image_path,
                    "original_markdown": correction.original_markdown,
                    "corrected_markdown": correction.corrected_markdown,
                    "region_index": correction.region_index,
                    "correction_id": str(correction.id),
                }
                target.write(json.dumps(record, ensure_ascii=False) + "\n")
                stats.total_pairs += 1
                stats.correction_ids.append(str(correction.id))
                if document_id in holdout_documents:
                    stats.holdout_pairs += 1
                else:
                    stats.train_pairs += 1
    return stats


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
