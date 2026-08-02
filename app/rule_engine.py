from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

JsonDict = dict[str, Any]

@dataclass(frozen=True)
class RuleEngineConfig:
    version: str = "0.1.0"
    min_history_transactions: int = 8
    new_recipient_amount_multiplier: float = 3.0
    new_recipient_min_amount: float = 250_000.0
    high_amount_multiplier: float = 4.0
    high_amount_min_amount: float = 500_000.0
    velocity_1h_count: int = 5
    velocity_6h_count: int = 10
    repeated_amount_window_hours: float = 6.0
    repeated_amount_count: int = 3
    repeated_amount_tolerance_ratio: float = 0.01
    nearly_depleted_ratio: float = 0.05
    large_balance_impact_ratio: float = 0.80
    night_hours: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
    unusual_hour_max_share: float = 0.05
    critical_severity_threshold: float = 0.90
    additional_rule_bonus: float = 0.05
    rule_severities: Mapping[str, float] | None = None

    def severities(self) -> dict[str, float]:
        values = {
            "LIMITED_USER_HISTORY": 0.25,
            "NEW_RECIPIENT_HIGH_AMOUNT": 0.75,
            "AMOUNT_ABOVE_PERSONAL_BASELINE": 0.70,
            "HIGH_TRANSACTION_VELOCITY": 0.75,
            "BALANCE_NEARLY_DEPLETED": 0.90,
            "LARGE_BALANCE_IMPACT": 0.80,
            "REPEATED_SAME_AMOUNT": 0.65,
            "UNUSUAL_TRANSACTION_TIME": 0.45,
        }
        values.update(dict(self.rule_severities or {}))
        return {k: min(max(float(v), 0.0), 1.0) for k, v in values.items()}

def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError(f"Timestamp tidak valid: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default

def _prepare_history(history: Sequence[Mapping[str, Any]], current_time: datetime) -> list[dict[str, Any]]:
    rows = []
    for item in history:
        try:
            timestamp = _parse_datetime(item.get("timestamp"))
        except (TypeError, ValueError):
            continue
        if timestamp >= current_time:
            continue
        row = dict(item)
        row["_timestamp"] = timestamp
        row["_amount"] = max(_safe_float(item.get("amount")), 0.0)
        rows.append(row)
    rows.sort(key=lambda row: row["_timestamp"])
    return rows

class RuleEngine:
    """Rule Engine V0 untuk sinyal perhatian dan reason code."""

    ENGINE_NAME = "rule_engine_v0"

    def __init__(self, config: RuleEngineConfig | None = None) -> None:
        self.config = config or RuleEngineConfig()
        self.severity_map = self.config.severities()

    @classmethod
    def from_json(cls, path: str | Path) -> "RuleEngine":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload["night_hours"] = tuple(payload.get("night_hours", (0, 1, 2, 3, 4, 5)))
        return cls(RuleEngineConfig(**payload))

    def evaluate(self, transaction: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> JsonDict:
        current_time = _parse_datetime(transaction.get("timestamp"))
        amount = max(_safe_float(transaction.get("amount")), 0.0)
        recipient_id = transaction.get("recipient_id")
        balance_before = _safe_float(transaction.get("balance_before"), -1.0)
        balance_after = _safe_float(transaction.get("balance_after"), -1.0)
        clean_history = _prepare_history(history, current_time)
        history_count = len(clean_history)
        history_amounts = [row["_amount"] for row in clean_history if row["_amount"] > 0]
        historical_median = float(median(history_amounts)) if history_amounts else 0.0
        triggered = []

        def trigger(rule_id: str, condition: bool, details: Mapping[str, Any], *, critical: bool | None = None) -> None:
            if not condition:
                return
            severity = self.severity_map[rule_id]
            is_critical = severity >= self.config.critical_severity_threshold if critical is None else critical
            triggered.append({
                "rule_id": rule_id,
                "severity": round(float(severity), 6),
                "critical": bool(is_critical),
                "details": dict(details),
            })

        trigger("LIMITED_USER_HISTORY", history_count < self.config.min_history_transactions, {
            "history_transaction_count": history_count,
            "minimum_required": self.config.min_history_transactions,
        }, critical=False)

        prior_recipients = {row.get("recipient_id") for row in clean_history if row.get("recipient_id") not in (None, "")}
        is_new_recipient = recipient_id not in (None, "") and history_count > 0 and recipient_id not in prior_recipients
        new_recipient_required_amount = max(
            self.config.new_recipient_min_amount,
            historical_median * self.config.new_recipient_amount_multiplier,
        )
        trigger("NEW_RECIPIENT_HIGH_AMOUNT", is_new_recipient and amount >= new_recipient_required_amount, {
            "amount": amount,
            "historical_median": historical_median,
            "required_amount": new_recipient_required_amount,
        })

        high_amount_required = max(
            self.config.high_amount_min_amount,
            historical_median * self.config.high_amount_multiplier,
        )
        trigger("AMOUNT_ABOVE_PERSONAL_BASELINE", bool(history_amounts) and amount >= high_amount_required, {
            "amount": amount,
            "historical_median": historical_median,
            "required_amount": high_amount_required,
        })

        def count_within(hours: float) -> int:
            seconds = hours * 3600.0
            return sum(1 for row in clean_history if 0 < (current_time - row["_timestamp"]).total_seconds() <= seconds)

        count_1h = count_within(1.0)
        count_6h = count_within(6.0)
        trigger("HIGH_TRANSACTION_VELOCITY", count_1h >= self.config.velocity_1h_count or count_6h >= self.config.velocity_6h_count, {
            "recent_transaction_count_1h": count_1h,
            "recent_transaction_count_6h": count_6h,
            "threshold_1h": self.config.velocity_1h_count,
            "threshold_6h": self.config.velocity_6h_count,
        })

        amount_to_balance_ratio = amount / balance_before if balance_before > 0 else 0.0
        remaining_balance_ratio = (
            balance_after / balance_before if balance_before > 0 and balance_after >= 0
            else max(balance_before - amount, 0.0) / balance_before if balance_before > 0
            else -1.0
        )
        trigger("BALANCE_NEARLY_DEPLETED", balance_before > 0 and 0.0 <= remaining_balance_ratio <= self.config.nearly_depleted_ratio, {
            "balance_before": balance_before,
            "balance_after": balance_after,
            "remaining_balance_ratio": remaining_balance_ratio,
            "threshold": self.config.nearly_depleted_ratio,
        })
        trigger("LARGE_BALANCE_IMPACT", balance_before > 0 and amount_to_balance_ratio >= self.config.large_balance_impact_ratio, {
            "amount": amount,
            "balance_before": balance_before,
            "amount_to_balance_ratio": amount_to_balance_ratio,
            "threshold": self.config.large_balance_impact_ratio,
        })

        repeated_window_seconds = self.config.repeated_amount_window_hours * 3600.0
        tolerance = max(amount * self.config.repeated_amount_tolerance_ratio, 1.0)
        repeated_count = sum(
            1 for row in clean_history
            if 0 < (current_time - row["_timestamp"]).total_seconds() <= repeated_window_seconds
            and abs(row["_amount"] - amount) <= tolerance
        )
        trigger("REPEATED_SAME_AMOUNT", repeated_count >= self.config.repeated_amount_count, {
            "amount": amount,
            "repeated_count": repeated_count,
            "window_hours": self.config.repeated_amount_window_hours,
            "threshold_count": self.config.repeated_amount_count,
        })

        if history_count > 0:
            same_hour_count = sum(1 for row in clean_history if row["_timestamp"].hour == current_time.hour)
            current_hour_share = same_hour_count / history_count
        else:
            same_hour_count = 0
            current_hour_share = 0.0
        trigger("UNUSUAL_TRANSACTION_TIME", history_count >= self.config.min_history_transactions and current_time.hour in self.config.night_hours and current_hour_share <= self.config.unusual_hour_max_share, {
            "hour": current_time.hour,
            "same_hour_history_count": same_hour_count,
            "history_transaction_count": history_count,
            "current_hour_share": current_hour_share,
            "maximum_share": self.config.unusual_hour_max_share,
        }, critical=False)

        severities = [item["severity"] for item in triggered]
        rule_score = min(1.0, max(severities) + self.config.additional_rule_bonus * max(len(triggered) - 1, 0)) if severities else 0.0
        return {
            "rule_score": round(float(rule_score), 6),
            "critical_rule_triggered": any(bool(item["critical"]) for item in triggered),
            "triggered_rule_count": len(triggered),
            "triggered_rules": triggered,
            "reason_codes": [item["rule_id"] for item in triggered],
            "diagnostics": {
                "history_transaction_count": history_count,
                "historical_amount_median": round(historical_median, 6),
                "is_new_recipient": is_new_recipient,
                "recent_transaction_count_1h": count_1h,
                "recent_transaction_count_6h": count_6h,
                "repeated_amount_count": repeated_count,
                "amount_to_balance_ratio": round(float(amount_to_balance_ratio), 6),
                "remaining_balance_ratio": round(float(remaining_balance_ratio), 6),
                "current_hour_share": round(float(current_hour_share), 6),
            },
            "engine_name": self.ENGINE_NAME,
            "engine_version": self.config.version,
        }
