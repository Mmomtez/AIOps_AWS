from __future__ import annotations

from datetime import datetime, timezone

from backend.schemas.log_event import LogEvent
from backend.schemas.metrics import Metrics
from backend.schemas.observation import DataQuality, LogSummary

TRACKED_LOG_KEYWORDS = ("error", "exception", "timeout", "failed", "refused", "killed")
OPTIONAL_METRIC_FIELDS = {
    "gpu_utilization",
    "gpu_memory_utilization",
    "gpu_encoder_session_count",
}
VOLUME_METRIC_FIELDS = {
    "volume_read_bytes",
    "volume_write_bytes",
    "volume_read_ops",
    "volume_write_ops",
}
METRIC_FIELD_TO_RAW_ID = {
    "cpu": "cpuutilization",
    "memory": "mem_used_percent",
    "gpu_utilization": "gpuutilization",
    "gpu_memory_utilization": "gpumemoryutilization",
    "gpu_encoder_session_count": "gpuencoderstatssessioncount",
    "network_in": "networkin",
    "network_out": "networkout",
    "network_packets_in": "networkpacketsin",
    "network_packets_out": "networkpacketsout",
    "disk_read_ops": "diskreadops",
    "disk_write_ops": "diskwriteops",
    "disk_read_bytes": "diskreadbytes",
    "disk_write_bytes": "diskwritebytes",
}
VOLUME_PREFIXES = {
    "volume_read_bytes": "volumereadbytes",
    "volume_write_bytes": "volumewritebytes",
    "volume_read_ops": "volumereadops",
    "volume_write_ops": "volumewriteops",
}


def summarize_logs(logs: list[LogEvent], sample_size: int = 3) -> LogSummary:
    error_count = 0
    warning_count = 0
    keywords_found: set[str] = set()
    sample_messages: list[str] = []

    for log in logs:
        message = log.message.strip()
        message_lower = message.lower()

        if "error" in message_lower:
            error_count += 1
        if "warning" in message_lower:
            warning_count += 1

        for keyword in TRACKED_LOG_KEYWORDS:
            if keyword in message_lower:
                keywords_found.add(keyword)

        if message and len(sample_messages) < sample_size:
            sample_messages.append(message[:240])

    return LogSummary(
        error_count=error_count,
        warning_count=warning_count,
        keywords=sorted(keywords_found),
        sample_messages=sample_messages,
    )


def build_metrics(instance_id: str, raw_metrics: dict[str, float | None]) -> Metrics:
    def value(raw_key: str) -> float:
        raw_value = raw_metrics.get(raw_key)
        return float(raw_value) if raw_value is not None else 0.0

    def sum_ebs(prefix: str) -> float:
        return float(
            sum(
                metric_value
                for metric_key, metric_value in raw_metrics.items()
                if metric_key.startswith(prefix) and metric_value is not None
            )
        )

    return Metrics(
        instance_id=instance_id,
        cpu=value("cpuutilization"),
        memory=value("mem_used_percent"),
        gpu_utilization=value("gpuutilization"),
        gpu_memory_utilization=value("gpumemoryutilization"),
        gpu_encoder_session_count=value("gpuencoderstatssessioncount"),
        network_in=value("networkin"),
        network_out=value("networkout"),
        network_packets_in=value("networkpacketsin"),
        network_packets_out=value("networkpacketsout"),
        disk_read_ops=value("diskreadops"),
        disk_write_ops=value("diskwriteops"),
        disk_read_bytes=value("diskreadbytes"),
        disk_write_bytes=value("diskwritebytes"),
        volume_read_bytes=sum_ebs("volumereadbytes"),
        volume_write_bytes=sum_ebs("volumewritebytes"),
        volume_read_ops=sum_ebs("volumereadops"),
        volume_write_ops=sum_ebs("volumewriteops"),
    )


def detect_missing_metrics(raw_metrics: dict[str, float | None]) -> list[str]:
    missing_metrics: list[str] = []

    for field_name, raw_id in METRIC_FIELD_TO_RAW_ID.items():
        if field_name in OPTIONAL_METRIC_FIELDS:
            continue
        if raw_metrics.get(raw_id) is None:
            missing_metrics.append(field_name)

    for field_name, prefix in VOLUME_PREFIXES.items():
        has_volume_metric = any(
            metric_key.startswith(prefix) and metric_value is not None
            for metric_key, metric_value in raw_metrics.items()
        )
        if not has_volume_metric:
            missing_metrics.append(field_name)

    return sorted(missing_metrics)


def compute_data_quality(
    *,
    observation_time: datetime,
    metrics_timestamp: datetime,
    logs: list[LogEvent],
    missing_metrics: list[str],
    freshness_threshold_seconds: int = 900,
) -> DataQuality:
    if observation_time.tzinfo is None:
        observation_time = observation_time.replace(tzinfo=timezone.utc)
    if metrics_timestamp.tzinfo is None:
        metrics_timestamp = metrics_timestamp.replace(tzinfo=timezone.utc)

    metrics_age_seconds = max((observation_time - metrics_timestamp).total_seconds(), 0.0)

    latest_log_timestamp = max((log.timestamp for log in logs), default=None)
    if latest_log_timestamp and latest_log_timestamp.tzinfo is None:
        latest_log_timestamp = latest_log_timestamp.replace(tzinfo=timezone.utc)

    logs_age_seconds = None
    if latest_log_timestamp is not None:
        logs_age_seconds = max((observation_time - latest_log_timestamp).total_seconds(), 0.0)

    expected_metrics_count = len(METRIC_FIELD_TO_RAW_ID) - len(OPTIONAL_METRIC_FIELDS) + len(VOLUME_METRIC_FIELDS)
    present_metrics_count = max(expected_metrics_count - len(missing_metrics), 0)
    metrics_completeness = present_metrics_count / expected_metrics_count if expected_metrics_count else 1.0
    logs_completeness = 1.0 if logs else 0.0
    completeness_score = round((metrics_completeness * 0.8) + (logs_completeness * 0.2), 4)

    candidate_ages = [metrics_age_seconds]
    if logs_age_seconds is not None:
        candidate_ages.append(logs_age_seconds)
    freshness_seconds = max(candidate_ages) if candidate_ages else 0.0
    is_fresh = freshness_seconds <= freshness_threshold_seconds

    return DataQuality(
        freshness_seconds=round(freshness_seconds, 3),
        metrics_age_seconds=round(metrics_age_seconds, 3),
        logs_age_seconds=round(logs_age_seconds, 3) if logs_age_seconds is not None else None,
        completeness_score=completeness_score,
        missing_data_points=len(missing_metrics),
        has_logs=bool(logs),
        is_fresh=is_fresh,
    )
