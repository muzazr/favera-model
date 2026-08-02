from app.rule_engine import RuleEngine

def test_rule_engine_balance_impact():
    engine = RuleEngine()
    transaction = {
        "timestamp": "2026-08-02T10:00:00+07:00",
        "amount": 900_000,
        "recipient_id": "new-recipient",
        "balance_before": 1_000_000,
        "balance_after": 100_000,
    }
    history = [
        {"timestamp": f"2026-08-01T{hour:02d}:00:00+07:00", "amount": 50_000, "recipient_id": "known-recipient"}
        for hour in range(8)
    ]
    result = engine.evaluate(transaction, history)
    assert 0.0 <= result["rule_score"] <= 1.0
    assert "LARGE_BALANCE_IMPACT" in result["reason_codes"]
