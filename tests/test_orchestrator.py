from app.fusion import FusionEngine
from app.global_ranker import FixedGlobalRanker, NullGlobalRanker
from app.orchestrator import Model1Orchestrator
from app.personal_anomaly import PersonalAnomalyScorer
from app.rule_engine import RuleEngine


def _history():
    return [
        {
            "transaction_at": f"2026-08-01T{8 + index:02d}:00:00+07:00",
            "amount": 50_000,
            "counterparty_id": "known-recipient",
        }
        for index in range(8)
    ]


def _transaction():
    return {
        "transaction_id": "txn-test",
        "transaction_at": "2026-08-02T17:00:00+07:00",
        "amount": 900_000,
        "counterparty_id": "new-recipient",
        "balance_before": 1_000_000,
        "balance_after": 100_000,
    }


def test_orchestrator_returns_complete_contract():
    orchestrator = Model1Orchestrator(
        global_ranker=FixedGlobalRanker(probability=0.95, percentile=0.997),
        personal_anomaly=PersonalAnomalyScorer(),
        rule_engine=RuleEngine(),
        fusion_engine=FusionEngine(),
    )

    result = orchestrator.evaluate(
        request_id="req-test",
        user_id="user-test",
        transaction=_transaction(),
        history=_history(),
    )

    assert result["request_id"] == "req-test"
    assert result["transaction_id"] == "txn-test"
    assert 0.0 <= result["attention_score"] <= 1.0
    assert set(result["components"]) == {"global", "personal", "rules", "fusion"}
    assert result["processing"]["status"] == "success"
    assert isinstance(result["reason_codes"], list)


def test_orchestrator_assess_batch_returns_openapi_contract():
    orchestrator = Model1Orchestrator(
        global_ranker=FixedGlobalRanker(probability=0.95, percentile=0.997),
        personal_anomaly=PersonalAnomalyScorer(),
        rule_engine=RuleEngine(),
        fusion_engine=FusionEngine(),
    )

    payload = {
        "request_id": "req-batch-001",
        "user_id": "user-001",
        "current_transactions": [_transaction()],
        "historical_transactions": _history(),
    }

    result = orchestrator.assess_batch(payload)

    assert result["request_id"] == "req-batch-001"
    assert isinstance(result["assessments"], list)
    assert len(result["assessments"]) == 1
    assessment = result["assessments"][0]
    assert assessment["transaction_id"] == "txn-test"
    assert assessment["risk_band"] in ("normal", "unusual", "needs_confirmation")
    assert assessment["personal_baseline_status"] == "available"
    assert isinstance(result["processing_ms"], float)


def test_orchestrator_still_works_without_global_artifact():
    orchestrator = Model1Orchestrator(
        global_ranker=NullGlobalRanker(),
        personal_anomaly=PersonalAnomalyScorer(),
        rule_engine=RuleEngine(),
        fusion_engine=FusionEngine(),
    )

    result = orchestrator.evaluate(
        transaction=_transaction(),
        history=_history(),
    )

    assert result["components"]["global"]["status"] == "unavailable"
    assert 0.0 <= result["attention_score"] <= 1.0

