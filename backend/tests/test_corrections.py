"""Correction lifecycle: draft → autosave → submit → approve/reject, plus
tenant isolation and the region_index bounds check."""

import uuid

import pytest
from sqlalchemy import select

from app.models import OcrResult, Page


@pytest.fixture()
def page_with_result(db, seed):
    company = seed["company_a"]
    from app.models import Document, DocumentStatus

    document = Document(
        company_id=company.id,
        original_filename=f"corr-{uuid.uuid4().hex[:8]}.pdf",
        content_sha256=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        mime_type="application/pdf",
        byte_size=10,
        storage_path="/dev/null",
        status=DocumentStatus.completed.value,
        page_count=1,
    )
    db.add(document)
    db.flush()
    page = Page(
        document_id=document.id,
        company_id=company.id,
        page_number=1,
        image_path="/dev/null",
        status="completed",
    )
    db.add(page)
    db.flush()
    result = OcrResult(
        page_id=page.id,
        company_id=company.id,
        markdown="# 請求書\n\n| 品目 | 金額 |\n| --- | --- |\n| A | ¥100 |",
        layout_json={"regions": [{"bbox": [0, 0, 1, 1], "kind": "title", "markdown": "# 請求書", "confidence": 0.9, "vertical": False}]},
        engine="mock",
        is_current=True,
    )
    db.add(result)
    db.commit()
    return page


def test_correction_lifecycle(client, auth, db, seed, page_with_result):
    created = client.post(
        f"/api/v1/pages/{page_with_result.id}/corrections",
        headers=auth("user_a"),
        json={"corrected_markdown": "# 請求書 (fixed)"},
    )
    assert created.status_code == 201, created.text
    correction = created.json()
    assert correction["status"] == "draft"
    assert correction["original_markdown"].startswith("# 請求書")

    updated = client.put(
        f"/api/v1/corrections/{correction['id']}",
        headers=auth("user_a"),
        json={"corrected_markdown": "# 請求書 (fixed v2)"},
    )
    assert updated.status_code == 200
    assert updated.json()["corrected_markdown"] == "# 請求書 (fixed v2)"

    submitted = client.post(
        f"/api/v1/corrections/{correction['id']}/submit", headers=auth("user_a")
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"  # approval required by default

    approved = client.post(
        f"/api/v1/corrections/{correction['id']}/approve", headers=auth("admin_a")
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # Approved corrections are frozen.
    frozen = client.put(
        f"/api/v1/corrections/{correction['id']}",
        headers=auth("user_a"),
        json={"corrected_markdown": "late edit"},
    )
    assert frozen.status_code == 409


def test_regular_user_cannot_approve(client, auth, seed, page_with_result):
    created = client.post(
        f"/api/v1/pages/{page_with_result.id}/corrections",
        headers=auth("user_a"),
        json={"corrected_markdown": "x"},
    ).json()
    client.post(f"/api/v1/corrections/{created['id']}/submit", headers=auth("user_a"))
    response = client.post(
        f"/api/v1/corrections/{created['id']}/approve", headers=auth("user_a")
    )
    assert response.status_code == 403


def test_region_index_bounds(client, auth, seed, page_with_result):
    response = client.post(
        f"/api/v1/pages/{page_with_result.id}/corrections",
        headers=auth("user_a"),
        json={"corrected_markdown": "x", "region_index": 5},
    )
    assert response.status_code == 400


def test_region_correction_pins_region_markdown(client, auth, seed, page_with_result):
    response = client.post(
        f"/api/v1/pages/{page_with_result.id}/corrections",
        headers=auth("user_a"),
        json={"corrected_markdown": "# 領収書", "region_index": 0},
    )
    assert response.status_code == 201
    assert response.json()["original_markdown"] == "# 請求書"


def test_corrections_invisible_across_tenants(client, auth, seed, page_with_result):
    created = client.post(
        f"/api/v1/pages/{page_with_result.id}/corrections",
        headers=auth("user_a"),
        json={"corrected_markdown": "x"},
    ).json()
    assert (
        client.put(
            f"/api/v1/corrections/{created['id']}",
            headers=auth("user_b"),
            json={"corrected_markdown": "hijack"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/pages/{page_with_result.id}/corrections",
            headers=auth("user_b"),
            json={"corrected_markdown": "x"},
        ).status_code
        == 404
    )
