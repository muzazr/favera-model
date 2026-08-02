from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

import joblib
import numpy as np
import pandas as pd

from app.reason_codes import GLOBAL_EXTREME_RISK_PATTERN


JsonDict = dict[str, Any]


@runtime_checkable
class GlobalRankerProtocol(Protocol):
    """Kontrak minimal global ranker untuk Model 1 orchestrator."""

    def score(self, global_features: Mapping[str, Any] | None) -> JsonDict:
        ...


@dataclass(frozen=True)
class GlobalRankerConfig:
    """Konfigurasi adapter global ranker V4.

    V4 dipakai sebagai extreme-risk ranker, bukan classifier mandiri.
    """

    version: str = "0.2.0"
    strong_percentile_threshold: float = 0.99
    strong_reason_code: str = GLOBAL_EXTREME_RISK_PATTERN

    def validate(self) -> None:
        if not 0.0 <= self.strong_percentile_threshold <= 1.0:
            raise ValueError(
                "strong_percentile_threshold harus berada pada rentang 0 sampai 1."
            )


class NullGlobalRanker:
    """Fallback aman saat artefak atau global features belum tersedia."""

    MODEL_NAME = "global_ranker_unavailable"

    def __init__(self, reason: str = "GLOBAL_ARTIFACT_NOT_CONFIGURED") -> None:
        self.reason = reason

    def score(self, global_features: Mapping[str, Any] | None) -> JsonDict:
        return {
            "status": "unavailable",
            "global_score": 0.0,
            "global_probability": None,
            "global_percentile": None,
            "global_signal_level": "NO_STRONG_GLOBAL_SIGNAL",
            "is_strong_global_signal": False,
            "reason_codes": [],
            "reason_details": [],
            "diagnostics": {"reason": self.reason},
            "model_name": self.MODEL_NAME,
            "model_version": "0.0.0",
        }


class FixedGlobalRanker:
    """Global ranker deterministik untuk test dan demo lokal."""

    MODEL_NAME = "fixed_global_ranker"

    def __init__(
        self,
        *,
        probability: float = 0.0,
        percentile: float | None = None,
        strong_percentile_threshold: float = 0.99,
        version: str = "fixed-v4-demo-0.2.0",
    ) -> None:
        self.probability = _clip01(probability)
        self.percentile = None if percentile is None else _clip01(percentile)
        self.strong_percentile_threshold = _clip01(strong_percentile_threshold)
        self.version = version

    def score(self, global_features: Mapping[str, Any] | None) -> JsonDict:
        strong = (
            self.percentile is not None
            and self.percentile >= self.strong_percentile_threshold
        )
        return _build_success_result(
            probability=self.probability,
            percentile=self.percentile,
            strong=strong,
            model_name=self.MODEL_NAME,
            model_version=self.version,
            reason_code=GLOBAL_EXTREME_RISK_PATTERN,
            diagnostics={"source": "fixed_demo"},
        )


class ArtifactGlobalRanker:
    """Adapter artefak global ranker hasil export notebook V4.

    Adapter hanya menerima feature mapping yang sudah sesuai feature contract.
    Feature builder mentah sengaja belum dipasang sampai kontrak input produksi
    dan notebook global V2 selesai diaudit.
    """

    def __init__(
        self,
        *,
        model_path: str | Path,
        feature_contract_path: str | Path,
        calibration_reference_path: str | Path,
        metadata_path: str | Path | None = None,
        config: GlobalRankerConfig | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.feature_contract_path = Path(feature_contract_path)
        self.calibration_reference_path = Path(calibration_reference_path)
        self.metadata_path = Path(metadata_path) if metadata_path else None

        if config is not None and config_path is not None:
            raise ValueError("Gunakan config atau config_path, bukan keduanya.")

        if config_path is not None:
            payload = _load_json(Path(config_path))
            config = GlobalRankerConfig(
                version=str(payload.get("version", "0.2.0")),
                strong_percentile_threshold=float(
                    payload.get("strong_percentile_threshold", 0.99)
                ),
                strong_reason_code=str(
                    payload.get(
                        "strong_reason_code",
                        GLOBAL_EXTREME_RISK_PATTERN,
                    )
                ),
            )

        self.config = config or GlobalRankerConfig()
        self.config.validate()

        for required_path in (
            self.model_path,
            self.feature_contract_path,
            self.calibration_reference_path,
        ):
            if not required_path.exists():
                raise FileNotFoundError(f"Artefak global ranker tidak ditemukan: {required_path}")

        self.model = joblib.load(self.model_path)
        self.feature_contract = _load_json(self.feature_contract_path)
        self.metadata = _load_json(self.metadata_path)

        features = (
            self.feature_contract.get("numeric_features")
            or self.feature_contract.get("features")
            or self.feature_contract.get("feature_names")
        )
        if not isinstance(features, list) or not features:
            raise ValueError(
                "Feature contract harus memiliki numeric_features berupa list non-kosong."
            )
        self.features = [str(feature) for feature in features]

        reference = np.asarray(
            np.load(self.calibration_reference_path),
            dtype=np.float64,
        ).reshape(-1)
        reference = reference[np.isfinite(reference)]
        if reference.size == 0:
            raise ValueError("Calibration score reference kosong atau tidak valid.")
        self.calibration_reference = np.sort(reference)

        model_feature_count = getattr(self.model, "n_features_in_", None)
        if model_feature_count is not None and int(model_feature_count) != len(self.features):
            raise ValueError(
                "Jumlah fitur model tidak sama dengan feature contract: "
                f"model={model_feature_count}, contract={len(self.features)}."
            )

        self.model_name = str(
            self.metadata.get("model_name", "global_ranker_v4_momtsim_v1")
        )
        self.model_version = str(self.metadata.get("model_version", "4.0.0"))

    @classmethod
    def from_artifact_directory(
        cls,
        artifact_dir: str | Path,
        *,
        config_path: str | Path | None = None,
        model_filename: str = "global_ranker_v4.joblib",
        feature_contract_filename: str = "feature_contract_v4.json",
        calibration_reference_filename: str = "calibration_score_reference_v4.npy",
        metadata_filename: str = "model_metadata_v4.json",
    ) -> "ArtifactGlobalRanker":
        directory = Path(artifact_dir)
        metadata_path = directory / metadata_filename
        return cls(
            model_path=directory / model_filename,
            feature_contract_path=directory / feature_contract_filename,
            calibration_reference_path=directory / calibration_reference_filename,
            metadata_path=metadata_path if metadata_path.exists() else None,
            config_path=config_path,
        )

    def score(self, global_features: Mapping[str, Any] | None) -> JsonDict:
        if global_features is None:
            return NullGlobalRanker("GLOBAL_FEATURES_NOT_PROVIDED").score(None)

        missing = [feature for feature in self.features if feature not in global_features]
        if missing:
            raise ValueError(
                "Global features tidak lengkap. Missing: " + ", ".join(missing[:20])
            )

        extra = sorted(set(global_features) - set(self.features))
        row: dict[str, float] = {}
        for feature in self.features:
            value = _finite_float(global_features[feature], feature)
            row[feature] = value

        matrix = pd.DataFrame([row], columns=self.features).astype("float32")
        probability = self._predict_probability(matrix)
        percentile = self._to_percentile(probability)
        strong = percentile >= self.config.strong_percentile_threshold

        return _build_success_result(
            probability=probability,
            percentile=percentile,
            strong=strong,
            model_name=self.model_name,
            model_version=self.model_version,
            reason_code=self.config.strong_reason_code,
            diagnostics={
                "feature_count": len(self.features),
                "ignored_extra_features": extra,
                "strong_percentile_threshold": self.config.strong_percentile_threshold,
            },
        )

    def _predict_probability(self, matrix: pd.DataFrame) -> float:
        if hasattr(self.model, "predict_proba"):
            prediction = np.asarray(self.model.predict_proba(matrix))
            if prediction.ndim == 2 and prediction.shape[1] >= 2:
                probability = float(prediction[0, 1])
            else:
                probability = float(prediction.reshape(-1)[0])
        elif hasattr(self.model, "predict"):
            probability = float(np.asarray(self.model.predict(matrix)).reshape(-1)[0])
        else:
            raise TypeError("Model tidak memiliki predict_proba atau predict.")

        if not math.isfinite(probability):
            raise ValueError("Global model menghasilkan probability non-finite.")
        return _clip01(probability)

    def _to_percentile(self, probability: float) -> float:
        position = np.searchsorted(
            self.calibration_reference,
            probability,
            side="right",
        )
        return _clip01(position / self.calibration_reference.size)


def _build_success_result(
    *,
    probability: float,
    percentile: float | None,
    strong: bool,
    model_name: str,
    model_version: str,
    reason_code: str,
    diagnostics: Mapping[str, Any],
) -> JsonDict:
    reason_details = (
        [
            {
                "code": reason_code,
                "source": "global_ranker",
                "severity": 1.0,
            }
        ]
        if strong
        else []
    )
    return {
        "status": "success",
        "global_score": 1.0 if strong else 0.0,
        "global_probability": round(float(probability), 8),
        "global_percentile": (
            None if percentile is None else round(float(percentile), 8)
        ),
        "global_signal_level": (
            "STRONG_GLOBAL_SIGNAL" if strong else "NO_STRONG_GLOBAL_SIGNAL"
        ),
        "is_strong_global_signal": bool(strong),
        "reason_codes": [reason_code] if strong else [],
        "reason_details": reason_details,
        "diagnostics": dict(diagnostics),
        "model_name": model_name,
        "model_version": model_version,
    }


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _finite_float(value: Any, feature: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Feature {feature!r} bukan angka valid.") from exc
    if not math.isfinite(numeric):
        raise ValueError(f"Feature {feature!r} harus finite.")
    return numeric


def _clip01(value: float) -> float:
    return min(max(float(value), 0.0), 1.0)
