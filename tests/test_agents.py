from datetime import datetime, timedelta, timezone

from backend.agents.monitoring_agent.monitoring_utils import (
    build_metrics,
    compute_data_quality,
    detect_missing_metrics,
    summarize_logs,
)
from backend.schemas.log_event import LogEvent


def test_summarize_logs_counts_keywords_and_samples():
    logs = [
        LogEvent(
            instance_id="i-123",
            timestamp=datetime.now(timezone.utc),
            log_group="group",
            log_stream="stream",
            message="ERROR connection timeout",
        ),
        LogEvent(
            instance_id="i-123",
            timestamp=datetime.now(timezone.utc),
            log_group="group",
            log_stream="stream",
            message="warning disk almost full",
        ),
    ]

    summary = summarize_logs(logs)

    assert summary.error_count == 1
    assert summary.warning_count == 1
    assert "timeout" in summary.keywords
    assert len(summary.sample_messages) == 2


def test_detect_missing_metrics_flags_required_missing_fields():
    raw_metrics = {
        "cpuutilization": 15.0,
        "networkin": 1.0,
    }

    missing = detect_missing_metrics(raw_metrics)

    assert "memory" in missing
    assert "network_out" in missing
    assert "gpu_utilization" not in missing


def test_compute_data_quality_combines_freshness_and_completeness():
    now = datetime.now(timezone.utc)
    logs = [
        LogEvent(
            instance_id="i-123",
            timestamp=now - timedelta(minutes=2),
            log_group="group",
            log_stream="stream",
            message="healthy",
        )
    ]

    quality = compute_data_quality(
        observation_time=now,
        metrics_timestamp=now - timedelta(minutes=1),
        logs=logs,
        missing_metrics=["memory"],
    )

    assert quality.is_fresh is True
    assert quality.has_logs is True
    assert quality.missing_data_points == 1
    assert quality.completeness_score < 1.0


def test_build_metrics_normalizes_raw_batch_values():
    raw_metrics = {
        "cpuutilization": 11.0,
        "mem_used_percent": 70.0,
        "networkin": 5.0,
        "networkout": 6.0,
        "networkpacketsin": 7.0,
        "networkpacketsout": 8.0,
        "diskreadops": 9.0,
        "diskwriteops": 10.0,
        "diskreadbytes": 11.0,
        "diskwritebytes": 12.0,
        "volumereadbytes_vol_a": 13.0,
        "volumewritebytes_vol_a": 14.0,
        "volumereadops_vol_a": 15.0,
        "volumewriteops_vol_a": 16.0,
    }

    metrics = build_metrics("i-123", raw_metrics)

    assert metrics.instance_id == "i-123"
    assert metrics.cpu == 11.0
    assert metrics.memory == 70.0
    assert metrics.volume_write_ops == 16.0
