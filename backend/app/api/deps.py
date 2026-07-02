import uuid
from datetime import datetime, timezone

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Device, User, UserRole
from app.services.security import decode_token, hash_device_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")
    return user


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.super_admin.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Super admin only")
    return user


def require_company_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.company_admin.value,):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Company admin only")
    return user


def require_company_member(user: User = Depends(get_current_user)) -> User:
    """Any tenant-scoped user (company admin or regular user)."""
    if user.company_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant users only")
    return user


def get_current_device(
    x_device_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Device:
    """Watcher-app auth: long-lived device token in the X-Device-Token header."""
    if not x_device_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing device token")
    device = (
        db.query(Device)
        .filter(Device.token_hash == hash_device_token(x_device_token))
        .one_or_none()
    )
    if device is None or device.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid device token")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return device
