import io


def _upload(client, headers, filename="請求書2026.pdf", content=b"%PDF-1.4 fake-invoice"):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def test_upload_and_get(client, auth, seed, no_celery):
    response = _upload(client, auth("user_a"))
    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["original_filename"] == "請求書2026.pdf"
    assert doc["status"] == "queued"
    assert no_celery, "OCR must be enqueued on upload"

    detail = client.get(f"/api/v1/documents/{doc['id']}", headers=auth("user_a"))
    assert detail.status_code == 200


def test_duplicate_upload_conflicts(client, auth, seed):
    content = b"%PDF-1.4 duplicate-target"
    first = _upload(client, auth("user_a"), "a.pdf", content)
    assert first.status_code == 201
    second = _upload(client, auth("user_a"), "b.pdf", content)
    assert second.status_code == 409
    assert second.json()["detail"]["existing_id"] == first.json()["id"]


def test_same_content_allowed_across_tenants(client, auth, seed):
    content = b"%PDF-1.4 shared-form-template"
    assert _upload(client, auth("user_a"), "form.pdf", content).status_code == 201
    assert _upload(client, auth("user_b"), "form.pdf", content).status_code == 201


def test_unsupported_type_rejected(client, auth, seed):
    response = client.post(
        "/api/v1/documents",
        headers=auth("user_a"),
        files={"file": ("run.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert response.status_code == 415


def test_thumbnail_404_before_rasterization_and_cross_tenant(client, auth, seed):
    doc = _upload(client, auth("user_a"), "thumb.pdf", b"%PDF-1.4 thumb-target").json()
    # No pages yet — grid view falls back to an icon.
    assert (
        client.get(f"/api/v1/documents/{doc['id']}/thumbnail", headers=auth("user_a")).status_code
        == 404
    )
    # Other tenants can't probe it either.
    assert (
        client.get(f"/api/v1/documents/{doc['id']}/thumbnail", headers=auth("user_b")).status_code
        == 404
    )


def test_list_filters_by_search(client, auth, seed):
    _upload(client, auth("user_a"), "見積書-searchable.pdf", b"%PDF-1.4 searchable")
    response = client.get("/api/v1/documents?q=searchable", headers=auth("user_a"))
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert "searchable" in items[0]["original_filename"]
