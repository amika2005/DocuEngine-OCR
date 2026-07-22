"""Reset the super admin password. Run after the DB is up:

    python -m app.db.reset_superadmin "NewPassword123"

If no password is given on the command line, SUPERADMIN_PASSWORD from the
environment/.env is used. The account is identified by SUPERADMIN_EMAIL.
"""

import sys

from sqlalchemy import select

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.models import User
from app.services.security import hash_password


def reset(new_password: str) -> None:
    settings = get_settings()
    db = get_sessionmaker()()
    try:
        user = db.scalar(select(User).where(User.email == settings.superadmin_email))
        if not user:
            print(f"NOT FOUND: no user with email {settings.superadmin_email}")
            sys.exit(1)
        user.password_hash = hash_password(new_password)
        db.commit()
        print(f"OK: password reset for {settings.superadmin_email} (role={user.role})")
    finally:
        db.close()


if __name__ == "__main__":
    password = sys.argv[1] if len(sys.argv) > 1 else get_settings().superadmin_password
    reset(password)
