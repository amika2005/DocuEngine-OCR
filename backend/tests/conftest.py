import os
import tempfile

# Test environment must be configured before any app import touches settings.
_tmp = tempfile.mkdtemp(prefix="docuengine-test-")
os.environ.update(
    {
        "DATABASE_URL_OVERRIDE": f"sqlite+pysqlite:///{_tmp}/test.db",
        "DATA_DIR": os.path.join(_tmp, "data"),
        "OCR_ENGINE": "mock",
        "SECRET_KEY": "test-secret",
        "DOCUENGINE_ENV": "test",
    }
)

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

get_settings.cache_clear()

import app.models  # noqa: F401 — register tables
from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker
from app.main import app as fastapi_app
from app.models import Company, User, UserRole
from app.services import documents as doc_service
from app.services.security import hash_password

Base.metadata.create_all(get_engine())


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    """Web/API tests never talk to a broker; the queue call is recorded instead."""
    queued: list[str] = []
    monkeypatch.setattr(
        doc_service, "enqueue_ocr", lambda document, priority=0: queued.append(str(document.id))
    )
    return queued


@pytest.fixture(scope="session")
def db():
    session = get_sessionmaker()()
    yield session
    session.close()


PASSWORD = "test-password-123"


def _make_user(db, company_id, email, role):
    user = User(
        company_id=company_id,
        email=email,
        password_hash=hash_password(PASSWORD),
        display_name=email.split("@")[0],
        role=role,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture(scope="session")
def seed(db):
    """Two tenants + a super admin — the fixture backbone for tenancy tests."""
    company_a = Company(name="株式会社アルファ", slug="alpha")
    company_b = Company(name="株式会社ベータ", slug="beta")
    db.add_all([company_a, company_b])
    db.commit()
    return {
        "company_a": company_a,
        "company_b": company_b,
        "super": _make_user(db, None, "root@sonasu.co.jp", UserRole.super_admin.value),
        "admin_a": _make_user(db, company_a.id, "admin@alpha.jp", UserRole.company_admin.value),
        "user_a": _make_user(db, company_a.id, "user@alpha.jp", UserRole.user.value),
        "admin_b": _make_user(db, company_b.id, "admin@beta.jp", UserRole.company_admin.value),
        "user_b": _make_user(db, company_b.id, "user@beta.jp", UserRole.user.value),
    }


@pytest.fixture(scope="session")
def client():
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth(client, seed):
    """auth('user_a') -> Authorization headers for that seeded account."""

    tokens: dict[str, dict] = {}

    def _headers(key: str) -> dict:
        if key not in tokens:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": seed[key].email, "password": PASSWORD},
            )
            assert response.status_code == 200, response.text
            tokens[key] = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return tokens[key]

    return _headers
