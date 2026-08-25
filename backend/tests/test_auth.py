def test_login_ok(client, seed):
    response = client.post(
        "/api/v1/auth/login", json={"email": "user@alpha.jp", "password": "test-password-123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] and body["refresh_token"]


def test_login_wrong_password(client, seed):
    response = client.post(
        "/api/v1/auth/login", json={"email": "user@alpha.jp", "password": "wrong"}
    )
    assert response.status_code == 401


def test_login_matches_email_with_trailing_cr(client, seed, db):
    user = seed["user_a"]
    original = user.email
    user.email = "user@alpha.jp\r"
    db.commit()
    try:
        response = client.post(
            "/api/v1/auth/login", json={"email": "user@alpha.jp", "password": "test-password-123"}
        )
        assert response.status_code == 200
    finally:
        user.email = original
        db.commit()


def test_me(client, auth, seed):
    response = client.get("/api/v1/auth/me", headers=auth("user_a"))
    assert response.status_code == 200
    assert response.json()["email"] == "user@alpha.jp"
    assert response.json()["role"] == "user"


def test_refresh_rotates_tokens(client, seed):
    login = client.post(
        "/api/v1/auth/login", json={"email": "user@alpha.jp", "password": "test-password-123"}
    ).json()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_access_token_rejected_as_refresh(client, seed):
    login = client.post(
        "/api/v1/auth/login", json={"email": "user@alpha.jp", "password": "test-password-123"}
    ).json()
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": login["access_token"]})
    assert response.status_code == 401


def test_role_guards(client, auth, seed):
    # Regular user cannot reach super-admin or company-admin surfaces.
    assert client.get("/api/v1/admin/companies", headers=auth("user_a")).status_code == 403
    assert client.get("/api/v1/company/users", headers=auth("user_a")).status_code == 403
    # Company admin cannot reach super-admin surface.
    assert client.get("/api/v1/admin/companies", headers=auth("admin_a")).status_code == 403
    # Super admin is not a tenant member: no document surface.
    assert client.get("/api/v1/documents", headers=auth("super")).status_code == 403
    # Unauthenticated.
    assert client.get("/api/v1/documents").status_code == 401
