from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_evaluate_batch_endpoint():
    client = TestClient(app)
    payload = {
        "request_id": "req_api_batch_01",
        "user_id": "usr_001",
        "current_transactions": [
            {
                "transaction_id": "txn_001",
                "transaction_at": "2026-08-02T10:00:00+07:00",
                "amount": 500000.0,
                "counterparty_id": "rcp_001",
                "direction": "transfer",
            }
        ],
        "historical_transactions": [],
    }

    response = client.post("/v1/model1/evaluate-batch", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["request_id"] == "req_api_batch_01"
    assert len(res_data["assessments"]) == 1
    assessment = res_data["assessments"][0]
    assert assessment["transaction_id"] == "txn_001"
    assert assessment["risk_band"] in ("normal", "unusual", "needs_confirmation")
    assert assessment["personal_baseline_status"] == "insufficient_history"
    assert assessment["personal_model_score"] is None

