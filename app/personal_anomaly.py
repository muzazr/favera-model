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
class PersonalAnomalyConfig:
    version: str = "0.1.0"
    min_history_transactions: int = 8
    confidence_floor: float = 0.35
    mad_epsilon: float = 1e-6
    robust_z_start: float = 2.0
    robust_z_full: float = 6.0
    velocity_window_1h: float = 1.0
    velocity_window_6h: float = 6.0
    velocity_count_1h_full: int = 5
    velocity_count_6h_full: int = 10
    repeated_amount_window_hours: float = 6.0
    repeated_amount_tolerance_ratio: float = 0.01
    repeated_amount_full_count: int = 4
    balance_impact_start: float = 0.30
    balance_impact_full: float = 0.90
    night_hours: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
    time_frequency_smoothing: float = 1.0
    reason_threshold: float = 0.65
    component_weights: Mapping[str, float] | None = None

    def resolved_weights(self) -> dict[str, float]:
        weights = dict(self.component_weights or {
            "amount_deviation": 0.32,
            "recipient_novelty": 0.18,
            "velocity_anomaly": 0.18,
            "time_anomaly": 0.10,
            "repeated_amount": 0.10,
            "balance_impact": 0.12,
        })
        total = sum(max(float(v), 0.0) for v in weights.values())
        if total <= 0:
            raise ValueError("Jumlah bobot komponen harus lebih dari nol.")
        return {k: max(float(v), 0.0) / total for k, v in weights.items()}

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

def _clip01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)

def _linear_score(value: float, start: float, full: float) -> float:
    if full <= start:
        raise ValueError("Parameter full harus lebih besar daripada start.")
    if value <= start:
        return 0.0
    if value >= full:
        return 1.0
    return _clip01((value - start) / (full - start))

def _history_before(history: Sequence[Mapping[str, Any]], current_time: datetime) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for row in history:
        try:
            timestamp = _parse_datetime(row.get("timestamp"))
        except (TypeError, ValueError):
            continue
        if timestamp >= current_time:
            continue
        item = dict(row)
        item["_timestamp"] = timestamp
        item["_amount"] = max(_safe_float(row.get("amount")), 0.0)
        clean.append(item)
    clean.sort(key=lambda item: item["_timestamp"])
    return clean

def _median_absolute_deviation(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    center = float(median(values))
    mad = float(median([abs(value - center) for value in values]))
    return center, mad

class PersonalAnomalyScorer:
    """Mengukur seberapa tidak biasa transaksi terhadap histori pengguna."""

    MODEL_NAME = "personal_anomaly_v0"

    def __init__(self, config: PersonalAnomalyConfig | None = None) -> None:
        self.config = config or PersonalAnomalyConfig()
        self.weights = self.config.resolved_weights()

    @classmethod
    def from_json(cls, path: str | Path) -> "PersonalAnomalyScorer":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload["night_hours"] = tuple(payload.get("night_hours", (0, 1, 2, 3, 4, 5)))
        return cls(PersonalAnomalyConfig(**payload))

    def score(self, transaction: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> JsonDict:
        current_time = _parse_datetime(transaction.get("timestamp"))
        amount = max(_safe_float(transaction.get("amount")), 0.0)
        recipient_id = transaction.get("recipient_id")
        clean_history = _history_before(history, current_time)
        history_count = len(clean_history)
        cold_start = history_count < self.config.min_history_transactions

        amounts = [item["_amount"] for item in clean_history if item["_amount"] > 0]
        amount_center, amount_mad = _median_absolute_deviation(amounts)
        if amounts:
            robust_scale = 1.4826 * max(amount_mad, self.config.mad_epsilon)
            robust_z = abs(amount - amount_center) / robust_scale
            amount_deviation = _linear_score(robust_z, self.config.robust_z_start, self.config.robust_z_full)
            amount_available = True
        else:
            robust_z = amount_deviation = 0.0
            amount_available = False

        prior_recipients = {item.get("recipient_id") for item in clean_history if item.get("recipient_id") not in (None, "")}
        if recipient_id in (None, ""):
            recipient_novelty = 0.0
            recipient_available = False
        elif not prior_recipients:
            recipient_novelty = 0.5
            recipient_available = history_count > 0
        else:
            recipient_novelty = 0.0 if recipient_id in prior_recipients else 1.0
            recipient_available = True

        def count_within(hours: float) -> int:
            seconds = hours * 3600.0
            return sum(1 for item in clean_history if 0 < (current_time - item["_timestamp"]).total_seconds() <= seconds)

        count_1h = count_within(self.config.velocity_window_1h)
        count_6h = count_within(self.config.velocity_window_6h)
        velocity_anomaly = max(
            _clip01(count_1h / max(self.config.velocity_count_1h_full, 1)),
            _clip01(count_6h / max(self.config.velocity_count_6h_full, 1)),
        )

        if history_count > 0:
            hour_counts = [0] * 24
            for item in clean_history:
                hour_counts[item["_timestamp"].hour] += 1
            alpha = max(self.config.time_frequency_smoothing, 0.0)
            current_hour = current_time.hour
            smoothed_frequency = (hour_counts[current_hour] + alpha) / (history_count + 24.0 * alpha)
            maximum_frequency = (max(hour_counts) + alpha) / (history_count + 24.0 * alpha)
            time_anomaly = 1.0 - _clip01(smoothed_frequency / max(maximum_frequency, 1e-12))
            time_available = True
        else:
            smoothed_frequency = 0.0
            time_anomaly = 0.0
            time_available = False

        repeated_window_seconds = self.config.repeated_amount_window_hours * 3600.0
        tolerance = max(amount * self.config.repeated_amount_tolerance_ratio, 1.0)
        repeated_count = sum(
            1 for item in clean_history
            if 0 < (current_time - item["_timestamp"]).total_seconds() <= repeated_window_seconds
            and abs(item["_amount"] - amount) <= tolerance
        )
        repeated_amount = _clip01(repeated_count / max(self.config.repeated_amount_full_count, 1))

        balance_before = _safe_float(transaction.get("balance_before"), -1.0)
        balance_after = _safe_float(transaction.get("balance_after"), -1.0)
        if balance_before > 0:
            amount_to_balance_ratio = amount / balance_before
            balance_impact = _linear_score(amount_to_balance_ratio, self.config.balance_impact_start, self.config.balance_impact_full)
            remaining_balance_ratio = balance_after / balance_before if balance_after >= 0 else max(balance_before - amount, 0.0) / balance_before
            balance_available = True
        else:
            amount_to_balance_ratio = 0.0
            remaining_balance_ratio = -1.0
            balance_impact = 0.0
            balance_available = False

        components = {
            "amount_deviation": float(amount_deviation),
            "recipient_novelty": float(recipient_novelty),
            "velocity_anomaly": float(velocity_anomaly),
            "time_anomaly": float(time_anomaly),
            "repeated_amount": float(repeated_amount),
            "balance_impact": float(balance_impact),
        }
        availability = {
            "amount_deviation": amount_available,
            "recipient_novelty": recipient_available,
            "velocity_anomaly": history_count > 0,
            "time_anomaly": time_available,
            "repeated_amount": history_count > 0,
            "balance_impact": balance_available,
        }

        active_weight_total = sum(self.weights[name] for name, available in availability.items() if available)
        raw_score = (
            sum(components[name] * self.weights[name] for name, available in availability.items() if available) / active_weight_total
            if active_weight_total > 0 else 0.0
        )
        history_confidence = _clip01(history_count / max(self.config.min_history_transactions, 1))
        confidence_multiplier = self.config.confidence_floor + (1.0 - self.config.confidence_floor) * history_confidence
        personal_score = _clip01(raw_score * confidence_multiplier)

        reason_map = {
            "amount_deviation": "AMOUNT_ABOVE_PERSONAL_BASELINE",
            "recipient_novelty": "NEW_RECIPIENT",
            "velocity_anomaly": "HIGH_TRANSACTION_VELOCITY",
            "time_anomaly": "UNUSUAL_TRANSACTION_TIME",
            "repeated_amount": "REPEATED_AMOUNT",
            "balance_impact": "LARGE_BALANCE_IMPACT",
        }
        reason_details = []
        for component_name, value in components.items():
            if availability[component_name] and value >= self.config.reason_threshold:
                reason_details.append({
                    "code": reason_map[component_name],
                    "source": "personal_anomaly",
                    "component": component_name,
                    "severity": round(float(value), 6),
                })
        if cold_start:
            reason_details.append({
                "code": "LIMITED_USER_HISTORY",
                "source": "personal_anomaly",
                "component": "history_confidence",
                "severity": round(float(1.0 - history_confidence), 6),
            })

        personal_baseline_status = "insufficient_history" if cold_start else "available"
        final_personal_score = None if cold_start else round(float(personal_score), 6)

        return {
            "personal_score": round(float(personal_score), 6),
            "personal_model_score": final_personal_score,
            "personal_baseline_status": personal_baseline_status,
            "raw_personal_score": round(float(raw_score), 6),
            "history_confidence": round(float(history_confidence), 6),
            "cold_start": cold_start,
            "history_transaction_count": history_count,
            "components": {k: round(float(v), 6) for k, v in components.items()},
            "component_availability": availability,
            "diagnostics": {
                "amount_median_prior": round(float(amount_center), 6),
                "amount_mad_prior": round(float(amount_mad), 6),
                "amount_robust_zscore": round(float(robust_z), 6),
                "recent_transaction_count_1h": count_1h,
                "recent_transaction_count_6h": count_6h,
                "repeated_amount_count": repeated_count,
                "hour_smoothed_frequency": round(float(smoothed_frequency), 6),
                "amount_to_balance_ratio": round(float(amount_to_balance_ratio), 6),
                "remaining_balance_ratio": round(float(remaining_balance_ratio), 6),
            },
            "reason_codes": sorted({item["code"] for item in reason_details}),
            "reason_details": reason_details,
            "model_name": self.MODEL_NAME,
            "model_version": self.config.version,
        }
