from __future__ import annotations


def _first_queue_item(client, agent_key: str):
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    return next(item for item in payload["queue"] if item["agent_key"] == agent_key)


def test_dashboard_endpoints(client):
    index = client.get("/")
    assert index.status_code == 200
    assert 'id="root"' in index.text

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["overview"]["revenue_plan"] > 0
    assert payload["overview"]["revenue_forecast"] > 0
    revenue_row = next(row for row in payload["revenue_realization"]["rows"] if row["account_name"] == "PepsiCo")
    assert revenue_row["analysis"]["formula_inputs"]
    assert revenue_row["analysis"]["threshold_checks"]
    assert any(item["agent_key"] == "billing_trigger" for item in payload["queue"])

    report = client.get("/api/report")
    assert report.status_code == 200
    assert "narrative" in report.json()


def test_agent_followup_mock_and_action_approval(client):
    item = _first_queue_item(client, "revenue_realization")
    response = client.post(
        "/api/agent/draft-followup",
        json={
            "agent_key": item["agent_key"],
            "entity_type": item["entity_type"],
            "entity_id": item["entity_id"],
            "provider": "mock",
            "question": "Draft a follow-up for the revenue gap.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account_name"] == item["account_name"]
    assert "Action needed" in payload["email_subject"]
    assert payload["agent_key"] == "revenue_realization"

    approval = client.post(
        "/api/actions/approve",
        json={
            "agent_key": payload["agent_key"],
            "entity_type": payload["entity_type"],
            "entity_id": payload["entity_id"],
            "provider": "mock",
            "channel": "mock_email",
            "question": "Send the follow-up.",
        },
    )
    assert approval.status_code == 200
    approval_payload = approval.json()
    assert approval_payload["status"] == "Sent"
    assert approval_payload["notification_status"] == "Mock Sent"

    refreshed = client.get("/api/dashboard")
    assert refreshed.status_code == 200
    notifications = refreshed.json()["notifications"]
    assert len(notifications) >= 1
    assert notifications[0]["channel"] == "mock_email"


def test_threshold_update(client):
    dashboard = client.get("/api/dashboard")
    threshold = dashboard.json()["thresholds"][0]
    response = client.put(
        f"/api/thresholds/{threshold['id']}",
        json={"medium_value": threshold["medium_value"] + 1, "high_value": threshold["high_value"] + 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["medium_value"] == threshold["medium_value"] + 1
    assert payload["high_value"] == threshold["high_value"] + 1


def test_openai_provider_rejects_non_ascii_api_key(invalid_openai_client):
    providers = invalid_openai_client.get("/api/providers")
    assert providers.status_code == 200
    openai = next(item for item in providers.json() if item["provider"] == "openai")
    assert openai["available"] is False
    assert "non-ASCII characters" in openai["detail"]

    item = _first_queue_item(invalid_openai_client, "revenue_realization")
    response = invalid_openai_client.post(
        "/api/agent/draft-followup",
        json={
            "agent_key": item["agent_key"],
            "entity_type": item["entity_type"],
            "entity_id": item["entity_id"],
            "provider": "openai",
            "question": "Draft a follow-up for the revenue gap.",
        },
    )
    assert response.status_code == 503
    assert "non-ASCII characters" in response.json()["detail"]


def test_workbook_download(client):
    workbook = client.get("/api/data/workbook")
    assert workbook.status_code == 200
    assert workbook.headers["content-type"].startswith("application/vnd.openxmlformats")
