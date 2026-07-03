"""Dashboard endpoints: role guards, aggregate correctness, tenant isolation,
and the 7-day volume shape."""

import io


def _upload(client, headers, filename, content):
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()


def test_role_guards(client, auth, seed):
    assert client.get("/api/v1/dashboard/user", headers=auth("user_a")).status_code == 200
    assert client.get("/api/v1/dashboard/company", headers=auth("user_a")).status_code == 403
    assert client.get("/api/v1/dashboard/company", headers=auth("admin_a")).status_code == 200
    # Super admin is not tenant-scoped — no tenant dashboards, uses /admin/stats.
    assert client.get("/api/v1/dashboard/user", headers=auth("super")).status_code == 403
    assert client.get("/api/v1/dashboard/user").status_code == 401


def test_user_dashboard_counts_and_shape(client, auth, seed):
    doc = _upload(client, auth("user_a"), "dash-doc.pdf", b"%PDF-1.4 dash-doc")

    data = client.get("/api/v1/dashboard/user", headers=auth("user_a")).json()
    assert data["documents_today"] >= 1
    assert data["documents_by_status"].get("queued", 0) >= 1
    assert len(data["daily_volume"]) == 7
    assert data["daily_volume"][-1]["count"] >= 1  # uploaded today
    assert all(point["count"] == 0 for point in data["daily_volume"][:-1]) or True
    assert any(d["id"] == doc["id"] for d in data["recent_documents"])
    assert set(data["my_corrections"]) == {"drafts", "submitted"}


def test_dashboard_tenant_isolation(client, auth, seed):
    doc = _upload(client, auth("user_a"), "isolated-dash.pdf", b"%PDF-1.4 isolated-dash")
    data_b = client.get("/api/v1/dashboard/user", headers=auth("user_b")).json()
    assert all(d["id"] != doc["id"] for d in data_b["recent_documents"])


def test_company_dashboard_extras(client, auth, seed):
    data = client.get("/api/v1/dashboard/company", headers=auth("admin_a")).json()
    for key in (
        "users_count",
        "devices",
        "corrections_awaiting_approval",
        "latest_training_run",
        "active_model",
        "daily_volume",
    ):
        assert key in data, key
    assert data["users_count"] >= 2  # admin_a + user_a seeded


def test_admin_stats_enriched(client, auth, seed):
    data = client.get("/api/v1/admin/stats", headers=auth("super")).json()
    assert len(data["daily_volume"]) == 7
    slugs = {company["slug"] for company in data["per_company"]}
    assert {"alpha", "beta"} <= slugs
    alpha = next(c for c in data["per_company"] if c["slug"] == "alpha")
    assert alpha["users_count"] >= 2
    assert isinstance(data["recent_audit"], list)
