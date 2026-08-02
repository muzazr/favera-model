from __future__ import annotations

import json
from pathlib import Path

from app.fusion import FusionEngine
from app.global_ranker import FixedGlobalRanker
from app.orchestrator import Model1Orchestrator
from app.personal_anomaly import PersonalAnomalyScorer
from app.rule_engine import RuleEngine


PROJECT_ROOT = Path(__file__).resolve().parents[1]

orchestrator = Model1Orchestrator(
    global_ranker=FixedGlobalRanker(
        probability=0.94,
        percentile=0.995,
    ),
    personal_anomaly=PersonalAnomalyScorer.from_json(
        PROJECT_ROOT / "config" / "personal_anomaly_v0.json"
    ),
    rule_engine=RuleEngine.from_json(
        PROJECT_ROOT / "config" / "rule_engine_v0.json"
    ),
    fusion_engine=FusionEngine.from_json(
        PROJECT_ROOT / "config" / "fusion_v0.json"
    ),
)

current_transactions = [
    {
        "transaction_id": "txn_demo_001",
        "transaction_at": "2026-08-02T17:00:00+07:00",
        "amount": 900_000,
        "counterparty_id": "recipient-new",
        "balance_before": 1_000_000,
        "balance_after": 100_000,
        "direction": "transfer",
        "category": "TRANSFER",
        "currency": "IDR",
    }
]

historical_transactions = [
    {
        "transaction_id": f"history_{index}",
        "transaction_at": f"2026-08-01T{8 + index:02d}:00:00+07:00",
        "amount": 50_000 + index * 2_000,
        "counterparty_id": "recipient-known",
        "direction": "transfer",
        "category": "TRANSFER",
        "currency": "IDR",
    }
    for index in range(8)
]

payload = {
    "request_id": "req_demo_001",
    "user_id": "user_demo",
    "family_id": "family_demo",
    "current_transactions": current_transactions,
    "historical_transactions": historical_transactions,
    "household_context": {
        "essential_budget_remaining": 500000.0,
        "unconfirmed_transaction_count": 0,
        "large_transaction_threshold": 1000000.0,
        "active_goal_progress": 0.5,
    },
}

result = orchestrator.assess_batch(payload)

print(json.dumps(result, indent=2, ensure_ascii=False))

