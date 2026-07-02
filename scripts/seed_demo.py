"""Development seed: a demo tenant with an admin + user, so the web UI is
usable immediately after `make dev` + migrations.

    cd backend && uv run python ../scripts/seed_demo.py
"""

from sqlalchemy import select

from app.db.session import get_sessionmaker
from app.models import Company, User, UserRole
from app.services.security import hash_password

DEMO = {
    "company": {"name": "デモ株式会社", "name_kana": "デモカブシキガイシャ", "slug": "demo"},
    "admin": {"email": "admin@demo.jp", "password": "demo-admin-pw", "name": "デモ管理者"},
    "user": {"email": "user@demo.jp", "password": "demo-user-pw", "name": "デモユーザー"},
}


def main() -> None:
    db = get_sessionmaker()()
    try:
        company = db.scalar(select(Company).where(Company.slug == DEMO["company"]["slug"]))
        if company is None:
            company = Company(**DEMO["company"])
            db.add(company)
            db.flush()
            print(f"created company: {company.name}")

        for key, role in (("admin", UserRole.company_admin), ("user", UserRole.user)):
            spec = DEMO[key]
            if not db.scalar(select(User).where(User.email == spec["email"])):
                db.add(
                    User(
                        company_id=company.id,
                        email=spec["email"],
                        password_hash=hash_password(spec["password"]),
                        display_name=spec["name"],
                        role=role.value,
                    )
                )
                print(f"created {role.value}: {spec['email']} / {spec['password']}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
