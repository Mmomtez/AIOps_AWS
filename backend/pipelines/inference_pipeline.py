# Model inference pipeline
# backend/pipelines/inference_pipeline.py

import json
from pathlib import Path

from backend.schemas.anomaly_result import AnomalyResult


FEATURE_THRESHOLDS = {
    "cpu": 80.0,
    "memory": 80.0,
    "network_in": 1_000_000.0,
    "network_out": 1_000_000.0,
    "volume_write_bytes": 10_000_000.0,
}


def load_latest_metrics():
    path = Path("backend/data/metrics")
    files = sorted(path.glob("*.json"))

    if not files:
        return None

    latest_file = files[-1]
    with latest_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def detect_anomaly_rule_based(metrics: dict) -> AnomalyResult:
    triggered = []

    for feature, threshold in FEATURE_THRESHOLDS.items():
        value = float(metrics.get(feature, 0.0))
        if value > threshold:
            triggered.append(feature)

    is_anomaly = len(triggered) > 0

    if not is_anomaly:
        summary = "System behavior appears normal."
        severity = "low"
        score = 0.0
    else:
        severity = "medium" if len(triggered) <= 2 else "high"
        score = float(len(triggered))
        summary = f"Anomaly detected based on: {', '.join(triggered)}"

    return AnomalyResult(
        instance_id=metrics["instance_id"],
        is_anomaly=is_anomaly,
        severity=severity,
        score=score,
        summary=summary,
        triggered_features=triggered,
    )


def run_inference_pipeline():
    metrics = load_latest_metrics()

    if not metrics:
        print("No metrics history found.")
        return None

    result = detect_anomaly_rule_based(metrics)
    print("Anomaly result:", result)

    return result