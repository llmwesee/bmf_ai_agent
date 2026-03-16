from __future__ import annotations


def test_dashboard_endpoints(client):
    summary = client.get("/api/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["revenue_plan"] > 0
    assert payload["revenue_recognized"] > 0
    assert payload["high_risk_projects"] >= 1

    alerts = client.get("/api/alerts")
    assert alerts.status_code == 200
    assert len(alerts.json()) >= 1

    revenue = client.get("/api/revenue-table")
    assert revenue.status_code == 200
    assert any(row["account_name"] == "PepsiCo" for row in revenue.json())


def test_agent_followup_mock(client):
    response = client.post(
        "/api/agent/draft-followup",
        json={
            "account_name": "PepsiCo",
            "project_code": "PEP-DA-204",
            "focus_area": "revenue",
            "provider": "mock",
            "question": "Draft a follow-up for the revenue gap.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account_name"] == "PepsiCo"
    assert "PepsiCo" in payload["nudge"]
    assert "Action needed" in payload["email_subject"]
    assert payload["trace_id"] is None


def test_workbook_download_and_report(client):
    workbook = client.get("/api/data/workbook")
    assert workbook.status_code == 200
    assert workbook.headers["content-type"].startswith("application/vnd.openxmlformats")

    report = client.get("/api/report")
    assert report.status_code == 200
    payload = report.json()
    assert "narrative" in payload
    assert len(payload["top_accounts"]) >= 1
