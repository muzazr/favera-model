from __future__ import annotations

from typing import Any, Iterable, Mapping


GLOBAL_EXTREME_RISK_PATTERN = "GLOBAL_EXTREME_RISK_PATTERN"
GLOBAL_SIGNAL_UNAVAILABLE = "GLOBAL_SIGNAL_UNAVAILABLE"


def aggregate_reason_details(
    *collections: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Gabungkan reason code yang sama dan format sesuai kontrak 5-field OpenAPI."""
    merged: dict[str, dict[str, Any]] = {}

    for collection in collections:
        for item in collection:
            code = str(item.get("code") or item.get("rule_id") or "").strip()
            if not code:
                continue

            source = str(item.get("source") or "unknown")
            severity = _clip01(item.get("severity", 0.0))
            feature = item.get("feature") or item.get("component")
            observed_value = item.get("observed_value")
            baseline_value = item.get("baseline_value")
            explanation = item.get("explanation") or f"Triggered from {source} (severity {severity:.2f})"

            if code not in merged:
                merged[code] = {
                    "code": code,
                    "feature": str(feature) if feature else None,
                    "observed_value": observed_value,
                    "baseline_value": baseline_value,
                    "explanation": explanation,
                    "_severity": severity,
                }
            else:
                if severity > merged[code]["_severity"]:
                    merged[code]["_severity"] = severity
                    merged[code]["explanation"] = explanation
                if feature and not merged[code]["feature"]:
                    merged[code]["feature"] = str(feature)

    sorted_items = sorted(
        merged.values(),
        key=lambda row: (-float(row["_severity"]), str(row["code"])),
    )

    clean_details = []
    for row in sorted_items:
        clean_details.append({
            "code": row["code"],
            "feature": row["feature"],
            "observed_value": row["observed_value"],
            "baseline_value": row["baseline_value"],
            "explanation": row["explanation"],
        })
    return clean_details


def strings_to_reason_details(
    reason_codes: Iterable[str],
    *,
    source: str,
    severity: float,
) -> list[dict[str, Any]]:
    return [
        {
            "code": str(code),
            "feature": None,
            "observed_value": None,
            "baseline_value": None,
            "explanation": f"Signal from {source} (severity {severity:.2f})",
        }
        for code in reason_codes
        if str(code).strip()
    ]


def _clip01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(numeric, 0.0), 1.0)

