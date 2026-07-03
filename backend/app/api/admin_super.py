"""Sonasu super-admin endpoints: manage client companies, issue company-admin
logins, oversee global model versions and the audit trail."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_super_admin
from app.db.session import get_db
from app.models import (
    AuditLog,
    Company,
    Document,
    ModelVersion,
    ModelVersionStatus,
    User,
    UserRole,
)
from app.schemas.admin import CompanyCreate, CompanyOut, CompanyUpdate, UserCreate, UserOut
from app.schemas.document import ModelVersionOut
from app.services.audit import log_action
from app.services.security import hash_password

router = APIRouter(prefix="/admin", tags=["super-admin"], dependencies=[Depends(require_super_admin)])


@router.get("/companies", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.scalars(select(Company).order_by(Company.created_at)).all()


@router.post("/companies", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    if db.scalar(select(Company).where(Company.slug == body.slug)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use")
    company = Company(**body.model_dump())
    db.add(company)
    db.flush()
    log_action(db, "company.create", actor_user_id=admin.id, target_type="company",
               target_id=str(company.id), detail={"name": company.name})
    db.commit()
    return company


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


@router.patch("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    log_action(db, "company.update", actor_user_id=admin.id, target_type="company",
               target_id=str(company.id))
    db.commit()
    return company


@router.post(
    "/companies/{company_id}/admins",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def create_company_admin(
    company_id: uuid.UUID,
    body: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        company_id=company_id,
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=UserRole.company_admin.value,
    )
    db.add(user)
    db.flush()
    log_action(db, "user.create", company_id=company_id, actor_user_id=admin.id,
               target_type="user", target_id=str(user.id), detail={"role": user.role})
    db.commit()
    return user


@router.get("/stats")
def global_stats(db: Session = Depends(get_db)):
    from app.api.dashboard import _daily_volume

    document_counts = {
        str(row[0]): row[1]
        for row in db.execute(select(Document.company_id, func.count()).group_by(Document.company_id))
    }
    user_counts = {
        str(row[0]): row[1]
        for row in db.execute(
            select(User.company_id, func.count())
            .where(User.company_id.isnot(None))
            .group_by(User.company_id)
        )
    }
    companies = db.scalars(select(Company).order_by(Company.created_at)).all()
    recent_audit = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)
    ).all()

    return {
        "companies": len(companies),
        "users": db.scalar(select(func.count()).select_from(User)),
        "documents": db.scalar(select(func.count()).select_from(Document)),
        "documents_by_status": {
            row[0]: row[1]
            for row in db.execute(
                select(Document.status, func.count()).group_by(Document.status)
            )
        },
        "daily_volume": _daily_volume(db),
        "per_company": [
            {
                "id": str(company.id),
                "name": company.name,
                "slug": company.slug,
                "status": company.status,
                "documents_total": document_counts.get(str(company.id), 0),
                "users_count": user_counts.get(str(company.id), 0),
            }
            for company in companies
        ],
        "recent_audit": [
            {
                "action": entry.action,
                "target_type": entry.target_type,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in recent_audit
        ],
    }


@router.get("/audit-logs")
def audit_logs(
    limit: int = 100,
    company_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))
    if company_id:
        query = query.where(AuditLog.company_id == company_id)
    return [
        {
            "id": str(row.id),
            "company_id": str(row.company_id) if row.company_id else None,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": row.detail,
            "created_at": row.created_at.isoformat(),
        }
        for row in db.scalars(query)
    ]


@router.get("/model-versions", response_model=list[ModelVersionOut])
def list_model_versions(db: Session = Depends(get_db)):
    return db.scalars(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()


@router.post("/model-versions/{version_id}/activate", response_model=ModelVersionOut)
def activate_model_version(
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    version = db.get(ModelVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")
    from app.services.models_registry import activate_version

    activate_version(db, version)
    log_action(db, "model.activate", actor_user_id=admin.id, company_id=version.company_id,
               target_type="model_version", target_id=str(version.id))
    db.commit()
    return version
