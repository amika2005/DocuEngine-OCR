import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    action: str,
    *,
    company_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_device_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditLog(
            company_id=company_id,
            actor_user_id=actor_user_id,
            actor_device_id=actor_device_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            detail=detail or {},
            ip=ip,
        )
    )
