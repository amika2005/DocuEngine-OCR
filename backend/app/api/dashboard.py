"""Role-based dashboard aggregates. One round-trip per dashboard load."""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_company_admin, require_company_member
from app.db.session import get_db
from app.models import (
    Correction,
    CorrectionStatus,
    Device,
    Document,
    ModelVersion,
    ModelVersionStatus,
    Page,
    PageStatus,
    TrainingRun,
    User,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _documents_by_status(db: Session, company_id) -> dict[str, int]:
    return {
        row[0]: row[1]
        for row in db.execute(
            select(Document.status, func.count())
            .where(Document.company_id == company_id)
            .group_by(Document.status)
        )
    }


def _daily_volume(db: Session, company_id=None, days: int = 7) -> list[dict]:
    """Documents per calendar day (UTC) for the trailing week; every day present."""
    start = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    query = (
        select(func.date(Document.created_at), func.count())
        .where(Document.created_at >= datetime.combine(start, time.min, tzinfo=timezone.utc))
        .group_by(func.date(Document.created_at))
    )
    if company_id is not None:
        query = query.where(Document.company_id == company_id)
    counts = {str(row[0]): row[1] for row in db.execute(query)}
    return [
        {"date": str(start + timedelta(days=offset)), "count": counts.get(str(start + timedelta(days=offset)), 0)}
        for offset in range(days)
    ]


def _recent_documents(db: Session, company_id, limit: int = 6) -> list[dict]:
    documents = db.scalars(
        select(Document)
        .where(Document.company_id == company_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": str(document.id),
            "original_filename": document.original_filename,
            "status": document.status,
            "page_count": document.page_count,
            "created_at": document.created_at.isoformat(),
        }
        for document in documents
    ]


def _user_payload(db: Session, user: User) -> dict:
    today_start = datetime.combine(
        datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc
    )
    return {
        "documents_by_status": _documents_by_status(db, user.company_id),
        "documents_today": db.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.company_id == user.company_id, Document.created_at >= today_start)
        ),
        "processing_now": db.scalar(
            select(func.count())
            .select_from(Page)
            .where(
                Page.company_id == user.company_id,
                Page.status.in_([PageStatus.pending.value, PageStatus.processing.value]),
            )
        ),
        "recent_documents": _recent_documents(db, user.company_id),
        "my_corrections": {
            "drafts": db.scalar(
                select(func.count())
                .select_from(Correction)
                .where(
                    Correction.user_id == user.id,
                    Correction.status == CorrectionStatus.draft.value,
                )
            ),
            "submitted": db.scalar(
                select(func.count())
                .select_from(Correction)
                .where(
                    Correction.user_id == user.id,
                    Correction.status == CorrectionStatus.submitted.value,
                )
            ),
        },
        "daily_volume": _daily_volume(db, user.company_id),
    }


@router.get("/user")
def user_dashboard(
    user: User = Depends(require_company_member), db: Session = Depends(get_db)
) -> dict:
    return _user_payload(db, user)


@router.get("/company")
def company_dashboard(
    admin: User = Depends(require_company_admin), db: Session = Depends(get_db)
) -> dict:
    payload = _user_payload(db, admin)

    devices = db.scalars(
        select(Device).where(Device.company_id == admin.company_id).order_by(Device.created_at)
    ).all()
    latest_run = db.scalar(
        select(TrainingRun)
        .where(TrainingRun.company_id == admin.company_id)
        .order_by(TrainingRun.created_at.desc())
        .limit(1)
    )
    active_model = db.scalar(
        select(ModelVersion).where(
            ModelVersion.company_id == admin.company_id,
            ModelVersion.status == ModelVersionStatus.active.value,
        )
    ) or db.scalar(
        select(ModelVersion).where(
            ModelVersion.company_id.is_(None),
            ModelVersion.status == ModelVersionStatus.active.value,
        )
    )

    payload.update(
        {
            "users_count": db.scalar(
                select(func.count()).select_from(User).where(User.company_id == admin.company_id)
            ),
            "devices": [
                {
                    "id": str(device.id),
                    "name": device.name,
                    "status": device.status,
                    "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
                }
                for device in devices
            ],
            "corrections_awaiting_approval": db.scalar(
                select(func.count())
                .select_from(Correction)
                .where(
                    Correction.company_id == admin.company_id,
                    Correction.status == CorrectionStatus.submitted.value,
                )
            ),
            "latest_training_run": (
                {
                    "id": str(latest_run.id),
                    "status": latest_run.status,
                    "finished_at": latest_run.finished_at.isoformat()
                    if latest_run.finished_at
                    else None,
                }
                if latest_run
                else None
            ),
            "active_model": active_model.name if active_model else None,
        }
    )
    return payload
