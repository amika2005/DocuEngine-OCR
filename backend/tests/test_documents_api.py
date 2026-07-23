import io


def _upload(client, headers, filename="請求書2026.pdf", content=b"%PDF-1.4 fake-invoice"):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )


def test_document_visibility_private_shared(client, auth, seed, db, no_celery):
    from app.models import User, UserRole
    from app.services.security import hash_password

    # user_a's upload is private by default.
    doc = _upload(client, auth("user_a"), "vis-private.pdf", b"%PDF-1.4 vis").json()

    # A second regular user in the SAME company.
    other = User(
        company_id=seed["company_a"].id,
        email="other@alpha.jp",
        password_hash=hash_password("test-password-123"),
        display_name="other",
        role=UserRole.user.value,
    )
    db.add(other)
    db.commit()
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "other@alpha.jp", "password": "test-password-123"},
    ).json()["access_token"]
    other_auth = {"Authorization": f"Bearer {token}"}

    doc_url = f"/api/v1/documents/{doc['id']}"
    assert client.get(doc_url, headers=auth("user_a")).status_code == 200  # owner
    assert client.get(doc_url, headers=other_auth).status_code == 404  # other user: hidden
    assert client.get(doc_url, headers=auth("admin_a")).status_code == 200  # admin sees all
    other_ids = [d["id"] for d in client.get("/api/v1/documents", headers=other_auth).json()["items"]]
    assert doc["id"] not in other_ids

    # Share it → now the other user can see it.
    client.patch(f"{doc_url}/visibility?visibility=shared", headers=auth("user_a"))
    assert client.get(doc_url, headers=other_auth).status_code == 200


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


def test_same_content_allowed_across_users_in_one_company(client, auth, seed):
    # An admin scanning a document (private to them) must not block a regular
    # user in the same company from scanning the same file: dedup is per-uploader.
    content = b"%PDF-1.4 same-company-shared-scan"
    admin_doc = _upload(client, auth("admin_a"), "scan.pdf", content)
    assert admin_doc.status_code == 201
    user_doc = _upload(client, auth("user_a"), "scan.pdf", content)
    assert user_doc.status_code == 201
    assert user_doc.json()["id"] != admin_doc.json()["id"]


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
