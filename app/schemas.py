from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CanonicalTransaction(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_id: str | None = None
    transaction_at: datetime
    direction: str | None = None
    amount: float = Field(ge=0)
    currency: str = "IDR"
    description: str | None = None
    counterparty_name: str | None = None
    counterparty_id: str | None = None
    category: str | None = None
    payment_channel: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None
    external_transaction_id: str | None = None
    source_provider: str | None = None

    def to_internal_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "timestamp": self.transaction_at,
            "amount": self.amount,
            "recipient_id": self.counterparty_id,
            "direction": self.direction,
            "transaction_type": self.category or self.direction,
            "description": self.description,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "counterparty_name": self.counterparty_name,
            "currency": self.currency,
            "payment_channel": self.payment_channel,
            "source_provider": self.source_provider,
        }


class HouseholdContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    essential_budget_remaining: float | None = None
    unconfirmed_transaction_count: int | None = None
    large_transaction_threshold: float | None = None
    active_goal_progress: float | None = None


class BatchEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str | None = None
    user_id: str | None = None
    family_id: str | None = None
    current_transactions: list[CanonicalTransaction] = Field(default_factory=list)
    historical_transactions: list[CanonicalTransaction] = Field(default_factory=list)
    household_context: HouseholdContext | None = None


class ReasonDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    feature: str | None = None
    observed_value: Any = None
    baseline_value: Any = None
    explanation: str | None = None


class AnomalyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str | None = None
    anomaly_score: float
    risk_band: Literal["normal", "unusual", "needs_confirmation"]
    reason_codes: list[str] = Field(default_factory=list)
    reason_details: list[ReasonDetail] = Field(default_factory=list)
    recommended_action: str | None = None
    personal_baseline_status: Literal["available", "insufficient_history", "not_applicable"]
    global_model_score: float | None = None
    personal_model_score: float | None = None
    rule_score: float | None = None
    model_version: str
    preprocessing_version: str


class BatchEvaluateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    assessments: list[AnomalyAssessment]
    processing_ms: float | int


# Legacy schemas for backwards-compatibility with older internal endpoints/tests
class TransactionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_id: str | None = None
    timestamp: datetime
    amount: float = Field(ge=0)
    recipient_id: str | None = None
    direction: str | None = None
    transaction_type: str | None = None
    description: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None


class HistoryTransactionInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_id: str | None = None
    timestamp: datetime
    amount: float = Field(ge=0)
    recipient_id: str | None = None
    direction: str | None = None
    transaction_type: str | None = None
    description: str | None = None
    balance_before: float | None = None
    balance_after: float | None = None


class EvaluateRequest(BaseModel):
    request_id: str | None = None
    user_id: str | None = None
    transaction: TransactionInput
    history: list[HistoryTransactionInput] = Field(
        default_factory=list,
        max_length=5000,
    )
    global_features: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    request_id: str
    user_id: str | None = None
    transaction_id: str | None = None
    attention_score: float
    attention_level: str
    requires_confirmation: bool
    component_scores: dict[str, float]
    reason_codes: list[dict[str, Any]]
    components: dict[str, Any]
    versions: dict[str, Any]
    processing: dict[str, Any]

