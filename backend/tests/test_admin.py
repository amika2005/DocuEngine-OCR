"""Super-admin company management and company-admin user management flows."""


def test_super_admin_creates_company_and_admin(client, auth, seed):
    company = client.post(
        "/api/v1/admin/companies",
        headers=auth("super"),
        json={"name": "株式会社ガンマ", "slug": "gamma"},
    )
    assert company.status_code == 201, company.text

    duplicate_slug = client.post(
        "/api/v1/admin/companies",
        headers=auth("super"),
        json={"name": "another", "slug": "gamma"},
    )
    assert duplicate_slug.status_code == 409

    admin = client.post(
        f"/api/v1/admin/companies/{company.json()['id']}/admins",
        headers=auth("super"),
        json={
            "email": "admin@gamma.jp",
            "display_name": "ガンマ管理者",
            "password": "gamma-admin-pw",
        },
    )
    assert admin.status_code == 201
    assert admin.json()["role"] == "company_admin"

    login = client.post(
        "/api/v1/auth/login", json={"email": "admin@gamma.jp", "password": "gamma-admin-pw"}
    )
    assert login.status_code == 200


def test_company_admin_creates_user_and_user_can_login(client, auth, seed):
    created = client.post(
        "/api/v1/company/users",
        headers=auth("admin_a"),
        json={
            "email": "new-user@alpha.jp",
            "display_name": "新規ユーザー",
            "password": "new-user-pw-123",
            "role": "user",
        },
    )
    assert created.status_code == 201, created.text

    login = client.post(
        "/api/v1/auth/login", json={"email": "new-user@alpha.jp", "password": "new-user-pw-123"}
    )
    assert login.status_code == 200

    invalid_role = client.post(
        "/api/v1/company/users",
        headers=auth("admin_a"),
        json={
            "email": "evil@alpha.jp",
            "display_name": "x",
            "password": "password-123",
            "role": "super_admin",
        },
    )
    assert invalid_role.status_code == 400


def test_stats_and_audit_log(client, auth, seed):
    stats = client.get("/api/v1/admin/stats", headers=auth("super"))
    assert stats.status_code == 200
    assert stats.json()["companies"] >= 2

    logs = client.get("/api/v1/admin/audit-logs", headers=auth("super"))
    assert logs.status_code == 200
    actions = {entry["action"] for entry in logs.json()}
    assert "auth.login" in actions
