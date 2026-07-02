import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config import get_settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _make_token(sub: str, token_type: str, expires_delta: timedelta, **claims) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "type": token_type, "iat": now, "exp": now + expires_delta, **claims}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def create_access_token(user_id: uuid.UUID, role: str, company_id: uuid.UUID | None) -> str:
    settings = get_settings()
    return _make_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.access_token_minutes),
        role=role,
        company_id=str(company_id) if company_id else None,
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    return _make_token(str(user_id), "refresh", timedelta(days=settings.refresh_token_days))


def decode_token(token: str, expected_type: str) -> dict:
    """Raises jwt.PyJWTError on any problem."""
    payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload


# --- Device tokens (watcher app) ---
# Long random secrets; only the sha256 is stored server-side.

def generate_device_token() -> tuple[str, str]:
    """Returns (raw_token, token_hash). Raw token is shown to the admin exactly once."""
    raw = "dedev_" + secrets.token_urlsafe(36)
    return raw, hash_device_token(raw)


def hash_device_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
