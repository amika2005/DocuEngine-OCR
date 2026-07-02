"""Registers trained adapters in the model registry. A passing run produces a
`candidate` version — a human activates it in the web UI (never auto-deploy).
Rollback is activating the previous retired version; artifacts are never deleted."""

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import ModelKind, ModelVersion, ModelVersionStatus, TrainingRun
from trainer.evaluate import EvalReport


def sha256_dir(path: Path) -> str:
    """Stable digest over the adapter directory contents."""
    digest = hashlib.sha256()
    for file in sorted(path.rglob("*")):
        if file.is_file():
            digest.update(file.name.encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def register_candidate(
    db: Session,
    run: TrainingRun,
    company_id: uuid.UUID,
    adapter_dir: Path,
    report: EvalReport,
    kind: str = ModelKind.lora_adapter.value,
) -> ModelVersion:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    version = ModelVersion(
        name=f"{kind}-{stamp}",
        kind=kind,
        parent_id=run.base_model_version_id,
        company_id=company_id,
        artifact_path=str(adapter_dir),
        artifact_sha256=sha256_dir(adapter_dir) if adapter_dir.exists() else None,
        metrics={
            "holdout_cer": report.candidate_holdout_cer,
            "golden_cer": report.candidate_golden_cer,
            "golden_table_f1": report.candidate_golden_table_f1,
        },
        status=(
            ModelVersionStatus.candidate.value
            if report.passed
            else ModelVersionStatus.rejected.value
        ),
    )
    db.add(version)
    db.flush()
    run.produced_model_version_id = version.id
    return version
