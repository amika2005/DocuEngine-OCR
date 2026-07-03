"""Admin/correction mutations must emit SSE events so dashboards and list
pages update live. publish_event is captured per-module (it's imported into
each router's namespace)."""

import io

import pytest


@pytest.fixture()
def captured(monkeypatch):
    events: list[tuple[str, str]] = []  # (topic, action)

    def capture(company_id, topic, data):
        events.append((topic, str(data.get("action", ""))))

    for module in (
        "app.api.admin_company",
        "app.api.admin_super",
        "app.api.corrections",
        "app.api.documents",
        "app.api.ingest",
    ):
        monkeypatch.setattr(f"{module}.publish_event", capture)
    return events


def test_user_create_emits_event(client, auth, seed, captured):
    response = client.post(
        "/api/v1/company/users",
        headers=auth("admin_a"),
        json={
            "email": "live-user@alpha.jp",
            "display_name": "ライブ",
            "password": "live-user-pw-1",
            "role": "user",
        },
    )
    assert response.status_code == 201
    assert ("company.users.changed", "created") in captured


def test_device_create_and_delete_emit_events(client, auth, seed, captured):
    device = client.post(
        "/api/v1/company/devices", headers=auth("admin_a"), json={"name": "ライブ端末"}
    ).json()
    client.delete(f"/api/v1/company/devices/{device['id']}", headers=auth("admin_a"))
    assert ("company.devices.changed", "created") in captured
    assert ("company.devices.changed", "deleted") in captured


def test_document_upload_emits_event(client, auth, seed, captured):
    response = client.post(
        "/api/v1/documents",
        headers=auth("user_a"),
        files={"file": ("live.pdf", io.BytesIO(b"%PDF-1.4 live-event"), "application/pdf")},
    )
    assert response.status_code == 201
    assert ("documents.changed", "uploaded") in captured
