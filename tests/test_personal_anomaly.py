from app.personal_anomaly import PersonalAnomalyScorer

def test_personal_anomaly_contract():
    scorer = PersonalAnomalyScorer()
    transaction = {
        "timestamp": "2026-08-02T10:00:00+07:00",
        "amount": 1_000_000,
        "recipient_id": "new-recipient",
        "balance_before": 1_100_000,
        "balance_after": 100_000,
    }
    history = [
        {"timestamp": f"2026-08-01T{hour:02d}:00:00+07:00", "amount": 50_000 + hour * 1_000, "recipient_id": "known-recipient"}
        for hour in range(8)
    ]
    result = scorer.score(transaction, history)
    assert 0.0 <= result["personal_score"] <= 1.0
    assert result["history_transaction_count"] == 8
    assert result["cold_start"] is False
