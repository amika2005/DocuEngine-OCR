"""One-shot VPS login repair: strip CR from emails and set a known super-admin
password. Does not drop the database.

    python -m app.db.fix_vps_login TempLogin1234
"""

import sys

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import User, UserRole
from app.services.security import hash_password, verify_password


def main(password: str) -> None:
    password = password.strip()
    db = get_sessionmaker()()
    try:
        users = list(db.scalars(select(User)))
        if not users:
            print("NO USERS in this database — you may be on the wrong Postgres.")
            sys.exit(1)
        print("users:")
        for user in users:
            cleaned = (user.email or "").strip().replace("\r", "")
            print(f"  {user.email!r} -> {cleaned!r}  role={user.role} status={user.status}")
            user.email = cleaned
        super_admin = next((u for u in users if u.role == UserRole.super_admin.value), None)
        if super_admin is None:
            print("NO super_admin row")
            sys.exit(1)
        super_admin.password_hash = hash_password(password)
        db.commit()
        db.refresh(super_admin)
        ok = verify_password(password, super_admin.password_hash)
        print(f"reset {super_admin.email} verify={ok}")
        if not ok:
            sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "TempLogin1234")
