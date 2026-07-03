"""Masters API: CRUD role guards, tenancy isolation, CSV import."""

import io
import uuid


def _create_type(client, auth, name=None):
    response = client.post(
        "/api/v1/masters/types",
        headers=auth("admin_a"),
        json={
            "name": name or f"商品-{uuid.uuid4().hex[:6]}",
            "fields": [
                {"key": "name", "label": "商品名", "matchable": True, "required": True},
                {"key": "price", "label": "単価", "matchable": False, "required": False},
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_type_crud_and_guards(client, auth, seed):
    master_type = _create_type(client, auth)

    # Regular users can read, not write.
    assert client.get("/api/v1/masters/types", headers=auth("user_a")).status_code == 200
    assert (
        client.post(
            "/api/v1/masters/types", headers=auth("user_a"),
            json={"name": "x", "fields": [{"key": "a", "label": "A", "matchable": True}]},
        ).status_code
        == 403
    )

    # Duplicate name rejected; no matchable field rejected.
    duplicate = client.post(
        "/api/v1/masters/types", headers=auth("admin_a"),
        json={"name": master_type["name"],
              "fields": [{"key": "a", "label": "A", "matchable": True}]},
    )
    assert duplicate.status_code == 409
    invalid = client.post(
        "/api/v1/masters/types", headers=auth("admin_a"),
        json={"name": f"x-{uuid.uuid4().hex[:4]}",
              "fields": [{"key": "a", "label": "A", "matchable": False}]},
    )
    assert invalid.status_code == 400


def test_records_crud_and_validation(client, auth, seed):
    master_type = _create_type(client, auth)
    created = client.post(
        f"/api/v1/masters/types/{master_type['id']}/records",
        headers=auth("admin_a"),
        json={"data": {"name": "コピー用紙 A4", "price": "500", "junk_key": "dropped"}},
    )
    assert created.status_code == 201
    assert "junk_key" not in created.json()["data"]

    missing_required = client.post(
        f"/api/v1/masters/types/{master_type['id']}/records",
        headers=auth("admin_a"),
        json={"data": {"price": "100"}},
    )
    assert missing_required.status_code == 400

    listing = client.get(
        f"/api/v1/masters/types/{master_type['id']}/records?q=コピー",
        headers=auth("user_a"),
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_masters_tenant_isolation(client, auth, seed):
    master_type = _create_type(client, auth)
    record = client.post(
        f"/api/v1/masters/types/{master_type['id']}/records",
        headers=auth("admin_a"),
        json={"data": {"name": "秘密の商品"}},
    ).json()

    # Company B sees nothing of A's masters.
    types_b = client.get("/api/v1/masters/types", headers=auth("admin_b")).json()
    assert master_type["id"] not in {t["id"] for t in types_b}
    assert (
        client.get(
            f"/api/v1/masters/types/{master_type['id']}/records", headers=auth("admin_b")
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/masters/records/{record['id']}", headers=auth("admin_b"),
            json={"data": {"name": "hijack"}},
        ).status_code
        == 404
    )


def test_csv_import(client, auth, seed):
    master_type = _create_type(client, auth)
    csv_content = "﻿name,price\nトナー TN-29J,8000\nコピー用紙 A4,500\nトナー TN-29J,8000\n,\n"
    response = client.post(
        f"/api/v1/masters/types/{master_type['id']}/import",
        headers=auth("admin_a"),
        files={"file": ("masters.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["skipped"] == 1        # duplicate row
    assert len(body["errors"]) == 1   # empty row fails the required-field check

    bad_header = client.post(
        f"/api/v1/masters/types/{master_type['id']}/import",
        headers=auth("admin_a"),
        files={"file": ("bad.csv", io.BytesIO(b"foo,bar\n1,2\n"), "text/csv")},
    )
    assert bad_header.status_code == 400

    # Import is admin-only.
    forbidden = client.post(
        f"/api/v1/masters/types/{master_type['id']}/import",
        headers=auth("user_a"),
        files={"file": ("m.csv", io.BytesIO(b"name\nx\n"), "text/csv")},
    )
    assert forbidden.status_code == 403
