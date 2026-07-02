"""Company-admin endpoints: manage the tenant's own users and watcher devices,
view usage, trigger/inspect training, activate/rollback the tenant adapter."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_company_admin
from app.db.session import get_db
from app.models import (
    Company,
    Device,
    Document,
    ModelVersion,
    TrainingRun,
    TrainingRunStatus,
    User,
    UserRole,
)
from app.schemas.admin import (
    DeviceCreate,
    DeviceCreatedOut,
    DeviceOut,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.document import ModelVersionOut, TrainingRunOut
from app.services.audit import log_action
from app.services.models_registry import activate_version
from app.services.security import generate_device_token, hash_password

router = APIRouter(prefix="/company", tags=["company-admin"])


# --- Users ---

@router.get("/users", response_model=list[UserOut])
def list_users(admin: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    return db.scalars(
        select(User).where(User.company_id == admin.company_id).order_by(User.created_at)
    ).all()


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    if body.role not in (UserRole.user.value, UserRole.company_admin.value):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    company = db.get(Company, admin.company_id)
    current = db.scalar(
        select(func.count()).select_from(User).where(User.company_id == admin.company_id)
    )
    if current >= company.max_users:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User limit reached for this company")
    user = User(
        company_id=admin.company_id,
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    log_action(db, "user.create", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="user", target_id=str(user.id), detail={"role": user.role})
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.company_id != admin.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    updates = body.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in (
        UserRole.user.value,
        UserRole.company_admin.value,
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    for field, value in updates.items():
        setattr(user, field, value)
    log_action(db, "user.update", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="user", target_id=str(user.id))
    db.commit()
    return user


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    body: dict,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None or user.company_id != admin.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    new_password = body.get("new_password", "")
    if len(new_password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters")
    user.password_hash = hash_password(new_password)
    log_action(db, "user.reset_password", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="user", target_id=str(user.id))
    db.commit()


# --- Devices (watcher installations) ---

@router.get("/devices", response_model=list[DeviceOut])
def list_devices(admin: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    return db.scalars(
        select(Device).where(Device.company_id == admin.company_id).order_by(Device.created_at)
    ).all()


@router.post("/devices", response_model=DeviceCreatedOut, status_code=status.HTTP_201_CREATED)
def create_device(
    body: DeviceCreate,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    company = db.get(Company, admin.company_id)
    current = db.scalar(
        select(func.count()).select_from(Device).where(Device.company_id == admin.company_id)
    )
    if current >= company.max_devices:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device limit reached for this company")
    raw_token, token_hash = generate_device_token()
    device = Device(
        company_id=admin.company_id, name=body.name, token_hash=token_hash, created_by=admin.id
    )
    db.add(device)
    db.flush()
    log_action(db, "device.create", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="device", target_id=str(device.id))
    db.commit()
    return DeviceCreatedOut(
        **DeviceOut.model_validate(device, from_attributes=True).model_dump(),
        token=raw_token,
    )


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    device_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    device = db.get(Device, device_id)
    if device is None or device.company_id != admin.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found")
    db.delete(device)
    log_action(db, "device.delete", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="device", target_id=str(device_id))
    db.commit()


# --- Usage / training ---

@router.get("/usage")
def usage(admin: User = Depends(require_company_admin), db: Session = Depends(get_db)):
    by_status = {
        row[0]: row[1]
        for row in db.execute(
            select(Document.status, func.count())
            .where(Document.company_id == admin.company_id)
            .group_by(Document.status)
        )
    }
    return {
        "documents_total": sum(by_status.values()),
        "documents_by_status": by_status,
        "users": db.scalar(
            select(func.count()).select_from(User).where(User.company_id == admin.company_id)
        ),
        "devices": db.scalar(
            select(func.count()).select_from(Device).where(Device.company_id == admin.company_id)
        ),
    }


@router.get("/training-runs", response_model=list[TrainingRunOut])
def list_training_runs(
    admin: User = Depends(require_company_admin), db: Session = Depends(get_db)
):
    return db.scalars(
        select(TrainingRun)
        .where(TrainingRun.company_id == admin.company_id)
        .order_by(TrainingRun.created_at.desc())
    ).all()


@router.post("/training-runs", response_model=TrainingRunOut, status_code=status.HTTP_202_ACCEPTED)
def trigger_training(
    admin: User = Depends(require_company_admin), db: Session = Depends(get_db)
):
    run = TrainingRun(
        company_id=admin.company_id,
        status=TrainingRunStatus.pending.value,
        triggered_by="manual",
    )
    db.add(run)
    db.flush()
    log_action(db, "training.trigger", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="training_run", target_id=str(run.id))
    db.commit()
    from app.tasks.celery_app import celery_app

    celery_app.send_task(
        "trainer.run_training", args=[str(admin.company_id)],
        kwargs={"training_run_id": str(run.id)}, queue="training",
    )
    return run


@router.get("/model-versions", response_model=list[ModelVersionOut])
def list_model_versions(
    admin: User = Depends(require_company_admin), db: Session = Depends(get_db)
):
    return db.scalars(
        select(ModelVersion)
        .where(ModelVersion.company_id == admin.company_id)
        .order_by(ModelVersion.created_at.desc())
    ).all()


@router.post("/model-versions/{version_id}/activate", response_model=ModelVersionOut)
def activate_tenant_model(
    version_id: uuid.UUID,
    admin: User = Depends(require_company_admin),
    db: Session = Depends(get_db),
):
    version = db.get(ModelVersion, version_id)
    if version is None or version.company_id != admin.company_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model version not found")
    try:
        activate_version(db, version)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    log_action(db, "model.activate", company_id=admin.company_id, actor_user_id=admin.id,
               target_type="model_version", target_id=str(version.id))
    db.commit()
    return version
