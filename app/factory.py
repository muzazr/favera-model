from __future__ import annotations

import os
from pathlib import Path

from app.fusion import FusionEngine
from app.global_ranker import ArtifactGlobalRanker, NullGlobalRanker
from app.orchestrator import Model1Orchestrator
from app.personal_anomaly import PersonalAnomalyScorer
from app.rule_engine import RuleEngine


def build_orchestrator() -> Model1Orchestrator:
    root = Path(os.getenv("FAVERA_AI_ROOT", Path(__file__).resolve().parents[1]))

    personal_path = _resolve(
        root,
        os.getenv("PERSONAL_CONFIG_PATH", "config/personal_anomaly_v0.json"),
    )
    rule_path = _resolve(
        root,
        os.getenv("RULE_CONFIG_PATH", "config/rule_engine_v0.json"),
    )
    fusion_path = _resolve(
        root,
        os.getenv("FUSION_CONFIG_PATH", "config/fusion_v0.json"),
    )
    global_config_path = _resolve(
        root,
        os.getenv("GLOBAL_CONFIG_PATH", "config/global_ranker_v4.json"),
    )
    artifact_dir = _resolve(
        root,
        os.getenv(
            "GLOBAL_ARTIFACT_DIR",
            "artifacts/global_ranker_v4_momtsim_v1",
        ),
    )

    personal = PersonalAnomalyScorer.from_json(personal_path)
    rules = RuleEngine.from_json(rule_path)
    fusion = FusionEngine.from_json(fusion_path)

    try:
        global_ranker = ArtifactGlobalRanker.from_artifact_directory(
            artifact_dir,
            config_path=global_config_path if global_config_path.exists() else None,
        )
    except (FileNotFoundError, ValueError, OSError):
        global_ranker = NullGlobalRanker("GLOBAL_ARTIFACT_NOT_READY")

    return Model1Orchestrator(
        global_ranker=global_ranker,
        personal_anomaly=personal,
        rule_engine=rules,
        fusion_engine=fusion,
        fail_open_global=True,
        version="0.2.0",
    )


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path
