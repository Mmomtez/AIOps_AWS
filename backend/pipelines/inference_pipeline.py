# backend/pipelines/inference_pipeline.py

from backend.schemas.anomaly_result import AnomalyResult

FEATURE_THRESHOLDS = {
    "cpu": 80.0,
    "memory": 80.0,
    "network_in": 1_000_000.0,
    "network_out": 1_000_000.0,
    "volume_write_bytes": 10_000_000.0,
}


def detect_anomaly_rule_based(metrics: dict, log_summary: dict | None = None) -> AnomalyResult:
    triggered = []

    for feature, threshold in FEATURE_THRESHOLDS.items():
        value = float(metrics.get(feature, 0.0))
        if value > threshold:
            triggered.append(feature)

    log_summary = log_summary or {}
    error_count = int(log_summary.get("error_count", 0))
    keywords = log_summary.get("keywords", [])

    if error_count > 0 and "logs:error" not in triggered:
        triggered.append("logs:error")

    is_anomaly = len(triggered) > 0

    if not is_anomaly:
        severity = "low"
        score = 0.0
        summary = "System behavior appears normal."
    else:
        severity = "medium" if len(triggered) <= 2 else "high"
        score = float(len(triggered))
        summary = f"Anomaly detected based on: {', '.join(triggered)}"
        if keywords:
            summary += f". Log keywords found: {', '.join(keywords)}"

    return AnomalyResult(
        instance_id=metrics["instance_id"],
        is_anomaly=is_anomaly,
        severity=severity,
        score=score,
        summary=summary,
        triggered_features=triggered,
    )


def run_inference_pipeline(observation):
    metrics = observation.metrics.model_dump()
    log_summary = observation.log_summary.model_dump()

    result = detect_anomaly_rule_based(metrics, log_summary)
    print("Anomaly result:", result)
    return result