from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.agents.anomaly_agent.model_loader import (
    DEFAULT_ISOLATION_FOREST_PATH,
    load_anomaly_model,
)
from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.observation import Observation
from ml.models.anomaly_detection.isolation_forest import predict_single_metrics_point


class AnomalyAgent:
    def __init__(self, model_path: str | Path = DEFAULT_ISOLATION_FOREST_PATH):
        self.model_path = Path(model_path)
        self.model = load_anomaly_model(self.model_path)

    def detect(self, observation: Observation) -> AnomalyResult:
        metrics_row = observation.metrics.model_dump()
        prediction = predict_single_metrics_point(self.model, metrics_row)

        is_anomaly = bool(prediction["is_anomaly"])
        score = float(prediction["if_score"])
        triggered_features = self._infer_triggered_features(metrics_row, is_anomaly)

        return AnomalyResult(
            instance_id=observation.instance_id,
            timestamp=observation.timestamp,
            is_anomaly=is_anomaly,
            severity=self._severity_from_score(score, is_anomaly),
            score=score,
            summary=self._build_summary(is_anomaly, score, triggered_features),
            triggered_features=triggered_features,
        )

    def _severity_from_score(self, score: float, is_anomaly: bool) -> str:
        if not is_anomaly:
            return "low"

        if score < -0.15:
            return "high"

        if score < -0.05:
            return "medium"

        return "low"

    def _infer_triggered_features(self, metrics_row: dict[str, Any], is_anomaly: bool) -> list[str]:
        if not is_anomaly:
            return []

        thresholds = {
            "cpu": 80.0,
            "memory": 80.0,
            "gpu_utilization": 85.0,
            "gpu_memory_utilization": 85.0,
            "network_in": 1_000_000.0,
            "network_out": 1_000_000.0,
            "volume_write_bytes": 10_000_000.0,
        }

        triggered = []

        for feature, threshold in thresholds.items():
            value = float(metrics_row.get(feature, 0.0) or 0.0)
            if value >= threshold:
                triggered.append(feature)

        return triggered

    def _build_summary(
        self,
        is_anomaly: bool,
        score: float,
        triggered_features: list[str],
    ) -> str:
        if not is_anomaly:
            return f"System behavior appears normal. Isolation Forest score: {score:.4f}."

        if triggered_features:
            return (
                "Isolation Forest detected anomalous system behavior. "
                f"Likely contributing features: {', '.join(triggered_features)}. "
                f"Score: {score:.4f}."
            )

        return (
            "Isolation Forest detected anomalous system behavior, "
            f"but no simple threshold-based feature trigger was identified. Score: {score:.4f}."
        )


def detect_anomaly(observation: Observation) -> AnomalyResult:
    agent = AnomalyAgent()
    return agent.detect(observation)
