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
    assert "password" not in admin.json()
    assert admin.json()["email"] == "admin@gamma.jp"

    listed = client.get(
        f"/api/v1/admin/companies/{company.json()['id']}/admins",
        headers=auth("super"),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["email"] == "admin@gamma.jp"
    assert "password" not in listed.json()[0]
    assert "password_hash" not in listed.json()[0]

    companies = client.get("/api/v1/admin/companies", headers=auth("super")).json()
    gamma = next(item for item in companies if item["slug"] == "gamma")
    assert gamma["admin_count"] == 1


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


def test_super_admin_deactivates_and_deletes_company_admin(client, auth, seed):
    company = client.post(
        "/api/v1/admin/companies",
        headers=auth("super"),
        json={"name": "株式会社デルタ", "slug": "delta-admins"},
    )
    assert company.status_code == 201, company.text
    company_id = company.json()["id"]

    created = client.post(
        f"/api/v1/admin/companies/{company_id}/admins",
        headers=auth("super"),
        json={
            "email": "admin@delta.jp",
            "display_name": "デルタ管理者",
            "password": "delta-admin-pw",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    assert "password" not in created.json()

    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@delta.jp", "password": "delta-admin-pw"},
        ).status_code
        == 200
    )

    disabled = client.patch(
        f"/api/v1/admin/companies/{company_id}/admins/{user_id}",
        headers=auth("super"),
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@delta.jp", "password": "delta-admin-pw"},
        ).status_code
        == 403
    )

    reactivated = client.patch(
        f"/api/v1/admin/companies/{company_id}/admins/{user_id}",
        headers=auth("super"),
        json={"status": "active"},
    )
    assert reactivated.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@delta.jp", "password": "delta-admin-pw"},
        ).status_code
        == 200
    )

    deleted = client.delete(
        f"/api/v1/admin/companies/{company_id}/admins/{user_id}",
        headers=auth("super"),
    )
    assert deleted.status_code == 204
    remaining = client.get(
        f"/api/v1/admin/companies/{company_id}/admins",
        headers=auth("super"),
    )
    assert remaining.json() == []
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "admin@delta.jp", "password": "delta-admin-pw"},
        ).status_code
        == 401
    )


def test_super_admin_normalizes_slug_and_deletes_company(client, auth, seed):
    created = client.post(
        "/api/v1/admin/companies",
        headers=auth("super"),
        json={"name": "株式会社イプシロン", "slug": "Epsilon Co"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["slug"] == "epsilon-co"
    company_id = body["id"]

    listed = client.get("/api/v1/admin/companies", headers=auth("super")).json()
    assert any(item["id"] == company_id for item in listed)

    deleted = client.delete(
        f"/api/v1/admin/companies/{company_id}",
        headers=auth("super"),
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            f"/api/v1/admin/companies/{company_id}",
            headers=auth("super"),
        ).status_code
        == 404
    )
    remaining = client.get("/api/v1/admin/companies", headers=auth("super")).json()
    assert all(item["id"] != company_id for item in remaining)
    assert (
        client.delete(
            f"/api/v1/admin/companies/{company_id}",
            headers=auth("admin_a"),
        ).status_code
        == 403
    )
