from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class FusionConfig:
    """Fusion V0 yang transparan dan belum dikalibrasi end-to-end."""

    version: str = "0.2.0"
    global_weight: float = 0.20
    personal_weight: float = 0.50
    rule_weight: float = 0.30
    needs_attention_threshold: float = 0.45
    confirmation_threshold: float = 0.70
    personal_support_for_global: float = 0.50
    rule_support_for_global: float = 0.60
    personal_high_threshold: float = 0.80
    rule_support_for_personal: float = 0.60
    independent_signal_threshold: float = 0.65
    minimum_independent_signals: int = 2
    critical_rule_override: bool = True
    redistribute_unavailable_weight: bool = True

    def validate(self) -> None:
        values = {
            "global_weight": self.global_weight,
            "personal_weight": self.personal_weight,
            "rule_weight": self.rule_weight,
            "needs_attention_threshold": self.needs_attention_threshold,
            "confirmation_threshold": self.confirmation_threshold,
            "personal_support_for_global": self.personal_support_for_global,
            "rule_support_for_global": self.rule_support_for_global,
            "personal_high_threshold": self.personal_high_threshold,
            "rule_support_for_personal": self.rule_support_for_personal,
            "independent_signal_threshold": self.independent_signal_threshold,
        }
        for name, value in values.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} harus berada pada rentang 0 sampai 1.")
        if self.needs_attention_threshold > self.confirmation_threshold:
            raise ValueError(
                "needs_attention_threshold tidak boleh melebihi confirmation_threshold."
            )
        if self.minimum_independent_signals < 1:
            raise ValueError("minimum_independent_signals minimal 1.")
        if self.global_weight + self.personal_weight + self.rule_weight <= 0:
            raise ValueError("Jumlah bobot fusion harus lebih dari nol.")


class FusionEngine:
    """Menggabungkan tiga komponen tanpa mengubahnya menjadi vonis fraud."""

    ENGINE_NAME = "fusion_v0"

    def __init__(self, config: FusionConfig | None = None) -> None:
        self.config = config or FusionConfig()
        self.config.validate()

    @classmethod
    def from_json(cls, path: str | Path) -> "FusionEngine":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(FusionConfig(**payload))

    def combine(
        self,
        *,
        global_result: Mapping[str, Any],
        personal_result: Mapping[str, Any],
        rule_result: Mapping[str, Any],
    ) -> JsonDict:
        global_available = global_result.get("status") == "success"
        personal_available = (
            personal_result.get("personal_baseline_status") != "insufficient_history"
            and not bool(personal_result.get("cold_start", False))
        )
        global_score = _clip01(global_result.get("global_score", 0.0))
        raw_personal = personal_result.get("personal_score", 0.0)
        personal_score = _clip01(raw_personal) if personal_available else 0.0
        rule_score = _clip01(rule_result.get("rule_score", 0.0))
        strong_global = bool(global_result.get("is_strong_global_signal", False))
        critical_rule = bool(rule_result.get("critical_rule_triggered", False))

        weighted_score, effective_weights = self._weighted_score(
            global_score=global_score,
            personal_score=personal_score,
            rule_score=rule_score,
            global_available=global_available,
            personal_available=personal_available,
        )

        independent_signals = {
            "global": strong_global,
            "personal": personal_available and personal_score >= self.config.independent_signal_threshold,
            "rule": rule_score >= self.config.independent_signal_threshold,
        }
        independent_signal_count = sum(independent_signals.values())

        override_reason: str | None = None
        requires_confirmation = False

        if self.config.critical_rule_override and critical_rule:
            requires_confirmation = True
            override_reason = "CRITICAL_RULE_OVERRIDE"
        elif strong_global and personal_available and personal_score >= self.config.personal_support_for_global:
            requires_confirmation = True
            override_reason = "STRONG_GLOBAL_WITH_PERSONAL_SUPPORT"
        elif strong_global and rule_score >= self.config.rule_support_for_global:
            requires_confirmation = True
            override_reason = "STRONG_GLOBAL_WITH_RULE_SUPPORT"
        elif (
            personal_available
            and personal_score >= self.config.personal_high_threshold
            and rule_score >= self.config.rule_support_for_personal
        ):
            requires_confirmation = True
            override_reason = "HIGH_PERSONAL_WITH_RULE_SUPPORT"
        elif (
            weighted_score >= self.config.confirmation_threshold
            and independent_signal_count >= self.config.minimum_independent_signals
        ):
            requires_confirmation = True
            override_reason = "MULTI_SIGNAL_WEIGHTED_CONFIRMATION"

        if requires_confirmation:
            risk_band = "needs_confirmation"
        elif weighted_score >= self.config.needs_attention_threshold:
            risk_band = "unusual"
        else:
            risk_band = "normal"

        attention_level = risk_band

        return {
            "attention_score": round(float(weighted_score), 6),
            "attention_level": attention_level,
            "risk_band": risk_band,
            "requires_confirmation": requires_confirmation,
            "component_scores": {
                "global_score": round(float(global_score), 6) if global_available else None,
                "personal_score": round(float(personal_score), 6) if personal_available else None,
                "rule_score": round(float(rule_score), 6),
            },
            "effective_weights": {
                key: round(float(value), 6)
                for key, value in effective_weights.items()
            },
            "decision_factors": {
                "strong_global_signal": strong_global,
                "critical_rule_triggered": critical_rule,
                "independent_signals": independent_signals,
                "independent_signal_count": independent_signal_count,
                "override_reason": override_reason,
                "calibration_status": "PROVISIONAL_NOT_END_TO_END_CALIBRATED",
            },
            "engine_name": self.ENGINE_NAME,
            "engine_version": self.config.version,
        }

    def _weighted_score(
        self,
        *,
        global_score: float,
        personal_score: float,
        rule_score: float,
        global_available: bool,
        personal_available: bool = True,
    ) -> tuple[float, dict[str, float]]:
        weights = {
            "global": max(float(self.config.global_weight), 0.0),
            "personal": max(float(self.config.personal_weight), 0.0),
            "rule": max(float(self.config.rule_weight), 0.0),
        }

        if not global_available and self.config.redistribute_unavailable_weight:
            weights["global"] = 0.0

        if not personal_available and self.config.redistribute_unavailable_weight:
            weights["personal"] = 0.0

        total = sum(weights.values())
        if total <= 0:
            return 0.0, {"global": 0.0, "personal": 0.0, "rule": 0.0}

        normalized = {key: value / total for key, value in weights.items()}
        score = (
            normalized["global"] * global_score
            + normalized["personal"] * personal_score
            + normalized["rule"] * rule_score
        )
        return _clip01(score), normalized


def _clip01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(max(numeric, 0.0), 1.0)
