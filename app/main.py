from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.factory import build_orchestrator
from app.schemas import BatchEvaluateRequest, BatchEvaluateResponse, EvaluateRequest, EvaluateResponse


app = FastAPI(
    title="Favera Model 1 AI Service",
    version="0.2.0",
    description=(
        "Global extreme-risk ranker, personal anomaly, rule engine, "
        "provisional fusion, dan reason codes."
    ),
)

orchestrator = build_orchestrator()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "favera-model1-ai",
        "version": orchestrator.version,
        "global_ranker_adapter": type(orchestrator.global_ranker).__name__,
    }


@app.get("/version")
def version() -> dict[str, object]:
    return {
        "orchestrator": orchestrator.version,
        "personal_anomaly": orchestrator.personal_anomaly.config.version,
        "rule_engine": orchestrator.rule_engine.config.version,
        "fusion": orchestrator.fusion_engine.config.version,
        "global_ranker_adapter": type(orchestrator.global_ranker).__name__,
    }


@app.post("/v1/model1/evaluate", response_model=EvaluateResponse)
def evaluate(payload: EvaluateRequest) -> dict[str, object]:
    try:
        return orchestrator.evaluate(
            transaction=payload.transaction.model_dump(mode="json"),
            history=[item.model_dump(mode="json") for item in payload.history],
            global_features=payload.global_features,
            request_id=payload.request_id,
            user_id=payload.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Model 1 evaluation failed.",
        ) from exc


@app.post("/v1/model1/evaluate-batch", response_model=BatchEvaluateResponse)
def evaluate_batch(payload: BatchEvaluateRequest) -> dict[str, object]:
    try:
        return orchestrator.assess_batch(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Model 1 batch evaluation failed: {exc}",
        ) from exc

