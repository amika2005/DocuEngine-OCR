"""Watcher ingestion: device-token auth, handshake, batches, dedupe."""

import io

import pytest


@pytest.fixture(scope="module")
def device_token(client, auth):
    response = client.post(
        "/api/v1/company/devices", headers=auth("admin_a"), json={"name": "テストスキャナー"}
    )
    assert response.status_code == 201
    return response.json()["token"]


def _headers(token):
    return {"X-Device-Token": token}


def test_handshake(client, device_token, seed):
    response = client.post("/api/v1/ingest/handshake", headers=_headers(device_token))
    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == str(seed["company_a"].id)
    assert ".pdf" in body["allowed_extensions"]


def test_handshake_bad_token(client, seed):
    assert (
        client.post("/api/v1/ingest/handshake", headers=_headers("dedev_wrong")).status_code == 401
    )
    assert client.post("/api/v1/ingest/handshake").status_code == 401


def test_batch_upload_and_dedupe(client, device_token, seed, no_celery):
    batch = client.post("/api/v1/ingest/batches", headers=_headers(device_token)).json()

    content = b"%PDF-1.4 scanned-by-device"
    first = client.post(
        f"/api/v1/ingest/documents?batch_id={batch['id']}",
        headers=_headers(device_token),
        files={"file": ("scan001.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert first.status_code == 201
    assert no_celery, "ingest must enqueue OCR"

    duplicate = client.post(
        f"/api/v1/ingest/documents?batch_id={batch['id']}",
        headers=_headers(device_token),
        files={"file": ("scan001-copy.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["existing_id"] == first.json()["id"]

    status = client.get(
        f"/api/v1/ingest/documents/{first.json()['id']}/status", headers=_headers(device_token)
    )
    assert status.status_code == 200
    assert status.json()["status"] == "queued"

    closed = client.post(
        f"/api/v1/ingest/batches/{batch['id']}/close", headers=_headers(device_token)
    )
    assert closed.status_code == 200
    assert closed.json()["total_documents"] == 1


def test_device_cannot_touch_other_tenants_batch(client, auth, device_token, seed):
    other = client.post(
        "/api/v1/company/devices", headers=auth("admin_b"), json={"name": "B社スキャナー"}
    ).json()
    batch_a = client.post("/api/v1/ingest/batches", headers=_headers(device_token)).json()
    response = client.post(
        f"/api/v1/ingest/batches/{batch_a['id']}/close", headers=_headers(other["token"])
    )
    assert response.status_code == 404
