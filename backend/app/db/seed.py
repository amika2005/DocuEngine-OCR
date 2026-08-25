"""Idempotent seed: creates the Sonasu super admin and registers the shipped
base OCR model in the model registry. Run after migrations:

    python -m app.db.seed
"""

from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models import ModelKind, ModelVersion, ModelVersionStatus, User, UserRole
from app.services.security import hash_password


def seed() -> None:
    settings = get_settings()
    db = get_sessionmaker()()
    try:
        if not db.scalar(select(User).where(User.email == settings.superadmin_email.strip())):
            db.add(
                User(
                    company_id=None,
                    email=settings.superadmin_email.strip(),
                    password_hash=hash_password(settings.superadmin_password.strip()),
                    display_name=settings.superadmin_name.strip(),
                    role=UserRole.super_admin.value,
                )
            )
            print(f"seeded super admin: {settings.superadmin_email}")

        base_name = "paddleocr-vl-base"
        if not db.scalar(select(ModelVersion).where(ModelVersion.name == base_name)):
            db.add(
                ModelVersion(
                    name=base_name,
                    kind=ModelKind.base.value,
                    company_id=None,
                    artifact_path=str(settings.models_dir / "paddleocr-vl"),
                    status=ModelVersionStatus.active.value,
                )
            )
            print(f"seeded base model version: {base_name}")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
