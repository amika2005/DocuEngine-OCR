from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelVersion, ModelVersionStatus


def activate_version(db: Session, version: ModelVersion) -> None:
    """Flip the single active pointer for this (company, kind) scope. The previous
    active version is retired but its artifact is kept, so rollback is just
    activating it again."""
    if version.status not in (
        ModelVersionStatus.candidate.value,
        ModelVersionStatus.retired.value,
        ModelVersionStatus.active.value,
    ):
        raise ValueError(f"cannot activate a version in status {version.status}")

    current = db.scalar(
        select(ModelVersion).where(
            ModelVersion.company_id == version.company_id,
            ModelVersion.kind == version.kind,
            ModelVersion.status == ModelVersionStatus.active.value,
            ModelVersion.id != version.id,
        )
    )
    if current is not None:
        current.status = ModelVersionStatus.retired.value
        db.flush()
    version.status = ModelVersionStatus.active.value
    version.activated_at = datetime.now(timezone.utc)
