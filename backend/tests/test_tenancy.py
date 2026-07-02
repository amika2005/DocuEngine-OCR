"""Tenant isolation: whatever exists in company A must be a 404 for company B —
list endpoints must silently exclude, detail endpoints must not leak existence."""

import io


def _upload(client, headers, filename, content):
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_documents_are_invisible_across_tenants(client, auth, seed):
    doc = _upload(client, auth("user_a"), "tenant-a-secret.pdf", b"%PDF-1.4 tenant-a-secret")

    for path in (
        f"/api/v1/documents/{doc['id']}",
        f"/api/v1/documents/{doc['id']}/markdown",
        f"/api/v1/documents/{doc['id']}/pages",
    ):
        assert client.get(path, headers=auth("user_b")).status_code == 404, path

    listing = client.get("/api/v1/documents?q=tenant-a-secret", headers=auth("user_b")).json()
    assert listing["total"] == 0

    # ...and the owner can see it.
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=auth("user_a")).status_code == 200


def test_document_actions_blocked_across_tenants(client, auth, seed):
    doc = _upload(client, auth("user_a"), "tenant-a-actions.pdf", b"%PDF-1.4 tenant-a-actions")
    assert (
        client.post(f"/api/v1/documents/{doc['id']}/reprocess", headers=auth("user_b")).status_code
        == 404
    )
    assert (
        client.delete(f"/api/v1/documents/{doc['id']}", headers=auth("user_b")).status_code == 404
    )


def test_company_admin_cannot_touch_other_tenants_users(client, auth, seed):
    users_b = client.get("/api/v1/company/users", headers=auth("admin_b")).json()
    emails = {user["email"] for user in users_b}
    assert "user@alpha.jp" not in emails

    user_a_id = str(seed["user_a"].id)
    response = client.patch(
        f"/api/v1/company/users/{user_a_id}",
        headers=auth("admin_b"),
        json={"status": "disabled"},
    )
    assert response.status_code == 404


def test_devices_scoped_to_tenant(client, auth, seed):
    created = client.post(
        "/api/v1/company/devices", headers=auth("admin_a"), json={"name": "受付スキャナー"}
    )
    assert created.status_code == 201
    assert created.json()["token"].startswith("dedev_")
    device_id = created.json()["id"]

    devices_b = client.get("/api/v1/company/devices", headers=auth("admin_b")).json()
    assert device_id not in {device["id"] for device in devices_b}
    assert (
        client.delete(f"/api/v1/company/devices/{device_id}", headers=auth("admin_b")).status_code
        == 404
    )
