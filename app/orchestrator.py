from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Mapping, Sequence

from app.fusion import FusionEngine
from app.global_ranker import GlobalRankerProtocol, NullGlobalRanker
from app.personal_anomaly import PersonalAnomalyScorer
from app.reason_codes import aggregate_reason_details, strings_to_reason_details
from app.rule_engine import RuleEngine
from app.schemas import BatchEvaluateRequest, CanonicalTransaction


JsonDict = dict[str, Any]


class Model1Orchestrator:
    """Satu pintu masuk untuk Global, Personal, Rules, Fusion, dan reasons."""

    def __init__(
        self,
        *,
        global_ranker: GlobalRankerProtocol,
        personal_anomaly: PersonalAnomalyScorer,
        rule_engine: RuleEngine,
        fusion_engine: FusionEngine,
        fail_open_global: bool = True,
        version: str = "0.2.0",
    ) -> None:
        self.global_ranker = global_ranker
        self.personal_anomaly = personal_anomaly
        self.rule_engine = rule_engine
        self.fusion_engine = fusion_engine
        self.fail_open_global = fail_open_global
        self.version = version

    def assess_batch(self, payload: Mapping[str, Any] | BatchEvaluateRequest) -> JsonDict:
        started = time.perf_counter()
        if isinstance(payload, BatchEvaluateRequest):
            req_dict = payload.model_dump(mode="json")
        else:
            req_dict = dict(payload)

        request_id = str(req_dict.get("request_id") or uuid.uuid4())
        raw_current = req_dict.get("current_transactions", [])
        raw_history = req_dict.get("historical_transactions", [])

        current_list = []
        for index, item in enumerate(raw_current):
            if isinstance(item, CanonicalTransaction):
                txn_dict = item.to_internal_dict()
            elif isinstance(item, Mapping):
                txn_dict = self._normalize_canonical_dict(item)
            else:
                txn_dict = dict(item)
            current_list.append((index, txn_dict))

        history_list = []
        for item in raw_history:
            if isinstance(item, CanonicalTransaction):
                history_list.append(item.to_internal_dict())
            elif isinstance(item, Mapping):
                history_list.append(self._normalize_canonical_dict(item))
            else:
                history_list.append(dict(item))

        def _get_ts(t_dict: dict[str, Any]) -> datetime:
            val = t_dict.get("timestamp") or t_dict.get("transaction_at")
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            return datetime.min

        current_sorted = sorted(current_list, key=lambda pair: _get_ts(pair[1]))

        processed_current_history: list[dict[str, Any]] = []
        results_by_index: list[tuple[int, dict[str, Any]]] = []

        for original_index, txn in current_sorted:
            curr_ts = _get_ts(txn)
            dynamic_history = list(history_list) + [
                prior_txn for prior_txn in processed_current_history
                if _get_ts(prior_txn) < curr_ts
            ]

            eval_res = self.evaluate(
                transaction=txn,
                history=dynamic_history,
                global_features=None,
                request_id=request_id,
            )

            anomaly_score = float(eval_res["attention_score"])
            risk_band = eval_res.get("risk_band") or eval_res.get("attention_level") or "normal"
            if risk_band not in ("normal", "unusual", "needs_confirmation"):
                if risk_band == "needs_attention":
                    risk_band = "unusual"
                elif risk_band == "usual":
                    risk_band = "normal"
                else:
                    risk_band = "normal"

            raw_reason_details = eval_res.get("reason_codes") or []
            clean_reason_details = []
            reason_code_strings = set()
            if isinstance(raw_reason_details, list):
                for rd in raw_reason_details:
                    if isinstance(rd, dict):
                        code_str = str(rd.get("code", "")).strip()
                        if code_str:
                            reason_code_strings.add(code_str)
                        clean_reason_details.append({
                            "code": code_str,
                            "feature": rd.get("feature"),
                            "observed_value": rd.get("observed_value"),
                            "baseline_value": rd.get("baseline_value"),
                            "explanation": rd.get("explanation") or f"Reason {code_str}",
                        })
                    elif isinstance(rd, str) and rd.strip():
                        code_str = rd.strip()
                        reason_code_strings.add(code_str)
                        clean_reason_details.append({
                            "code": code_str,
                            "feature": None,
                            "observed_value": None,
                            "baseline_value": None,
                            "explanation": f"Reason {code_str}",
                        })

            if risk_band == "needs_confirmation":
                rec_action = "Perlu konfirmasi transaksi"
            elif risk_band == "unusual":
                rec_action = "Perhatian transaksi tidak biasa"
            else:
                rec_action = "Tidak ada tindakan yang diperlukan"

            personal_comp = eval_res["components"].get("personal", {})
            if personal_comp.get("cold_start") or len(dynamic_history) < 8:
                personal_status = "insufficient_history"
                personal_score = None
            else:
                personal_status = personal_comp.get("personal_baseline_status", "available")
                personal_score = personal_comp.get("personal_model_score")
                if personal_score is None and personal_comp.get("personal_score") is not None:
                    personal_score = float(personal_comp["personal_score"])

            global_comp = eval_res["components"].get("global", {})
            global_score = global_comp.get("global_score")
            if global_comp.get("status") != "success":
                global_score = None

            rule_comp = eval_res["components"].get("rules", {})
            rule_score = float(rule_comp["rule_score"]) if "rule_score" in rule_comp else None

            assessment = {
                "transaction_id": txn.get("transaction_id"),
                "anomaly_score": round(anomaly_score, 6),
                "risk_band": risk_band,
                "reason_codes": sorted(reason_code_strings),
                "reason_details": clean_reason_details,
                "recommended_action": rec_action,
                "personal_baseline_status": personal_status,
                "global_model_score": round(global_score, 6) if global_score is not None else None,
                "personal_model_score": round(personal_score, 6) if personal_score is not None else None,
                "rule_score": round(rule_score, 6) if rule_score is not None else None,
                "model_version": self.version,
                "preprocessing_version": "0.1.0",
            }
            results_by_index.append((original_index, assessment))
            processed_current_history.append(txn)

        results_by_index.sort(key=lambda pair: pair[0])
        assessments = [pair[1] for pair in results_by_index]

        processing_ms = round(_elapsed_ms(started), 3)

        return {
            "request_id": request_id,
            "assessments": assessments,
            "processing_ms": processing_ms,
        }

    def evaluate(
        self,
        *,
        transaction: Mapping[str, Any],
        history: Sequence[Mapping[str, Any]],
        global_features: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> JsonDict:
        started = time.perf_counter()
        normalized_txn = self._normalize_canonical_dict(transaction)
        self._validate_transaction(normalized_txn)

        request_id = request_id or str(uuid.uuid4())
        component_errors: dict[str, str] = {}
        component_latency: dict[str, float] = {}

        global_result = self._run_global(
            global_features=global_features,
            errors=component_errors,
            latency=component_latency,
        )
        personal_result = self._run_component(
            name="personal_anomaly",
            callback=lambda: self.personal_anomaly.score(normalized_txn, history),
            errors=component_errors,
            latency=component_latency,
            fallback={
                "personal_score": 0.0,
                "personal_model_score": None,
                "personal_baseline_status": "insufficient_history",
                "cold_start": True,
                "reason_codes": [],
                "reason_details": [],
                "model_name": "personal_anomaly_failed",
                "model_version": "0.0.0",
            },
        )
        rule_result = self._run_component(
            name="rule_engine",
            callback=lambda: self.rule_engine.evaluate(normalized_txn, history),
            errors=component_errors,
            latency=component_latency,
            fallback={
                "rule_score": 0.0,
                "critical_rule_triggered": False,
                "reason_codes": [],
                "triggered_rules": [],
                "engine_name": "rule_engine_failed",
                "engine_version": "0.0.0",
            },
        )

        fusion_started = time.perf_counter()
        fusion_result = self.fusion_engine.combine(
            global_result=global_result,
            personal_result=personal_result,
            rule_result=rule_result,
        )
        component_latency["fusion"] = _elapsed_ms(fusion_started)

        reason_codes = aggregate_reason_details(
            self._global_reason_details(global_result),
            self._personal_reason_details(personal_result),
            self._rule_reason_details(rule_result),
        )

        processing_status = "success" if not component_errors else "degraded"

        return {
            "request_id": request_id,
            "user_id": user_id,
            "transaction_id": normalized_txn.get("transaction_id"),
            "attention_score": fusion_result["attention_score"],
            "attention_level": fusion_result["attention_level"],
            "risk_band": fusion_result.get("risk_band", fusion_result["attention_level"]),
            "requires_confirmation": fusion_result["requires_confirmation"],
            "component_scores": fusion_result["component_scores"],
            "reason_codes": reason_codes,
            "components": {
                "global": global_result,
                "personal": personal_result,
                "rules": rule_result,
                "fusion": fusion_result,
            },
            "versions": {
                "orchestrator": self.version,
                "global_ranker": global_result.get("model_version", "0.0.0"),
                "personal_anomaly": personal_result.get("model_version", "0.0.0"),
                "rule_engine": rule_result.get("engine_version", "0.0.0"),
                "fusion": fusion_result.get("engine_version", "0.0.0"),
            },
            "processing": {
                "status": processing_status,
                "latency_ms": round(_elapsed_ms(started), 3),
                "component_latency_ms": {
                    key: round(value, 3)
                    for key, value in component_latency.items()
                },
                "component_errors": component_errors,
            },
        }

    def _run_global(
        self,
        *,
        global_features: Mapping[str, Any] | None,
        errors: dict[str, str],
        latency: dict[str, float],
    ) -> JsonDict:
        started = time.perf_counter()
        try:
            return self.global_ranker.score(global_features)
        except Exception as exc:
            if not self.fail_open_global:
                raise
            errors["global_ranker"] = str(exc)
            return NullGlobalRanker("GLOBAL_RANKER_EXECUTION_FAILED").score(None)
        finally:
            latency["global_ranker"] = _elapsed_ms(started)

    @staticmethod
    def _run_component(
        *,
        name: str,
        callback: Any,
        errors: dict[str, str],
        latency: dict[str, float],
        fallback: JsonDict,
    ) -> JsonDict:
        started = time.perf_counter()
        try:
            return callback()
        except Exception as exc:
            errors[name] = str(exc)
            return fallback
        finally:
            latency[name] = _elapsed_ms(started)

    @staticmethod
    def _global_reason_details(result: Mapping[str, Any]) -> list[dict[str, Any]]:
        details = result.get("reason_details")
        if isinstance(details, list):
            return [dict(item) for item in details if isinstance(item, Mapping)]
        return strings_to_reason_details(
            result.get("reason_codes", []),
            source="global_ranker",
            severity=float(result.get("global_score") or 0.0),
        )

    @staticmethod
    def _personal_reason_details(result: Mapping[str, Any]) -> list[dict[str, Any]]:
        details = result.get("reason_details")
        if isinstance(details, list):
            return [dict(item) for item in details if isinstance(item, Mapping)]
        return strings_to_reason_details(
            result.get("reason_codes", []),
            source="personal_anomaly",
            severity=float(result.get("personal_score") or 0.0),
        )

    @staticmethod
    def _rule_reason_details(result: Mapping[str, Any]) -> list[dict[str, Any]]:
        triggered = result.get("triggered_rules", [])
        details: list[dict[str, Any]] = []
        for item in triggered:
            if not isinstance(item, Mapping):
                continue
            details.append(
                {
                    "code": item.get("rule_id"),
                    "source": "rule_engine",
                    "severity": item.get("severity", result.get("rule_score", 0.0)),
                }
            )
        if details:
            return details
        return strings_to_reason_details(
            result.get("reason_codes", []),
            source="rule_engine",
            severity=float(result.get("rule_score") or 0.0),
        )

    @staticmethod
    def _normalize_canonical_dict(canonical_dict: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(canonical_dict)
        if "transaction_at" in item and "timestamp" not in item:
            item["timestamp"] = item["transaction_at"]
        if "counterparty_id" in item and "recipient_id" not in item:
            item["recipient_id"] = item["counterparty_id"]
        if "category" in item and "transaction_type" not in item:
            item["transaction_type"] = item["category"] or item.get("direction")
        return item

    @staticmethod
    def _validate_transaction(transaction: Mapping[str, Any]) -> None:
        if "timestamp" not in transaction and "transaction_at" not in transaction:
            raise ValueError("transaction.timestamp atau transaction_at wajib diisi.")
        timestamp = transaction.get("timestamp") or transaction.get("transaction_at")
        if isinstance(timestamp, str):
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif not isinstance(timestamp, datetime):
            raise ValueError("transaction timestamp tidak valid.")

        try:
            amount = float(transaction.get("amount", -1))
        except (TypeError, ValueError) as exc:
            raise ValueError("transaction.amount harus berupa angka.") from exc
        if amount < 0:
            raise ValueError("transaction.amount tidak boleh negatif.")


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0

