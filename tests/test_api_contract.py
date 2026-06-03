from fastapi.testclient import TestClient

from app.main import app


def test_health_is_liveness_only():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "healthy"
    assert "checks" not in response.json()["data"]


def test_aiops_diagnose_sse_contract():
    client = TestClient(app)

    with client.stream(
        "POST",
        "/api/aiops/diagnose",
        json={
            "session_id": "api-test",
            "mode": "demo",
            "namespace": "prod",
            "workload": "checkout-api",
            "question": "checkout-api 持续重启",
            "include_actions": True,
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "incident_normalized" in body
    assert "evidence_collected" in body
    assert "actions_created" in body
    assert "diagnosis_complete" in body
    assert "trace_id" in body
    assert "risk_summary" in body
    assert "evidence_coverage" in body
    assert "next_steps" in body
