from __future__ import annotations
import json
from pathlib import Path
from app.personal_anomaly import PersonalAnomalyScorer
from app.rule_engine import RuleEngine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
personal = PersonalAnomalyScorer.from_json(PROJECT_ROOT / "config" / "personal_anomaly_v0.json")
rules = RuleEngine.from_json(PROJECT_ROOT / "config" / "rule_engine_v0.json")

transaction = {
    "transaction_id": "txn_001",
    "timestamp": "2026-08-02T17:00:00+07:00",
    "amount": 450000,
    "recipient_id": "recipient-new",
    "balance_before": 500000,
    "balance_after": 50000,
}

history = [
    {"timestamp": "2026-08-01T10:00:00+07:00", "amount": 50000, "recipient_id": "recipient-a"},
    {"timestamp": "2026-08-01T12:00:00+07:00", "amount": 75000, "recipient_id": "recipient-b"},
    {"timestamp": "2026-08-01T14:00:00+07:00", "amount": 60000, "recipient_id": "recipient-a"},
    {"timestamp": "2026-08-01T16:00:00+07:00", "amount": 80000, "recipient_id": "recipient-c"},
    {"timestamp": "2026-08-02T08:00:00+07:00", "amount": 55000, "recipient_id": "recipient-a"},
    {"timestamp": "2026-08-02T09:00:00+07:00", "amount": 65000, "recipient_id": "recipient-b"},
    {"timestamp": "2026-08-02T10:00:00+07:00", "amount": 70000, "recipient_id": "recipient-c"},
    {"timestamp": "2026-08-02T11:00:00+07:00", "amount": 50000, "recipient_id": "recipient-a"},
]

print("PERSONAL ANOMALY")
print(json.dumps(personal.score(transaction, history), indent=2, ensure_ascii=False))
print("\nRULE ENGINE")
print(json.dumps(rules.evaluate(transaction, history), indent=2, ensure_ascii=False))
