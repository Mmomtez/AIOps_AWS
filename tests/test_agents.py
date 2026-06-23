from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.agents.action_agent.remediation_engine import ActionAgent
from backend.agents.anomaly_agent.anomaly_detector import AnomalyAgent
from backend.agents.monitoring_agent.monitoring_agent import MonitoringAgent
from backend.agents.monitoring_agent.monitoring_utils import (
    build_metrics,
    compute_data_quality,
    detect_missing_metrics,
    summarize_logs,
)
from backend.agents.orchestrator.workflow import run_incident_workflow_from_observation
from backend.agents.root_cause_agent.root_cause_agent import RootCauseAgent
from backend.schemas.action_schema import ActionResult
from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.diagnosis_result import DiagnosisResult
from backend.schemas.log_event import LogEvent
from ml.models.anomaly_detection.isolation_forest import (
    DEFAULT_METRIC_COLUMNS,
    save_isolation_forest_model,
    train_isolation_forest,
)


def _make_observation(cpu: float = 20.0, memory: float = 40.0):
    agent = MonitoringAgent(
        instance_id="i-test",
        aws_region="us-east-1",
        log_group_name="test-group",
    )
    return agent.package_observation(
        raw_metrics={
            "cpuutilization": cpu,
            "mem_used_percent": memory,
            "networkin": 1000.0,
            "networkout": 1000.0,
            "networkpacketsin": 10.0,
            "networkpacketsout": 10.0,
            "diskreadops": 0.0,
            "diskwriteops": 0.0,
            "diskreadbytes": 0.0,
            "diskwritebytes": 0.0,
            "volumereadbytes_vol_a": 0.0,
            "volumewritebytes_vol_a": 0.0,
            "volumereadops_vol_a": 0.0,
            "volumewriteops_vol_a": 0.0,
        },
        logs=[],
    )


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


def test_anomaly_agent_detect_smoke(tmp_path):
    rows = []
    for i in range(40):
        row = {column: 0.0 for column in DEFAULT_METRIC_COLUMNS}
        row["cpu"] = 20.0 + (i % 5)
        row["memory"] = 35.0 + (i % 7)
        row["network_in"] = 1000.0 + i
        row["network_out"] = 900.0 + i
        rows.append(row)

    model = train_isolation_forest(
        pd.DataFrame(rows),
        contamination=0.1,
        random_state=42,
    )
    model_path = tmp_path / "isolation_forest.joblib"
    save_isolation_forest_model(model, model_path)

    observation = _make_observation(cpu=90.0, memory=85.0)
    result = AnomalyAgent(model_path=model_path).detect(observation)

    assert result.instance_id == "i-test"
    assert result.is_anomaly is True
    assert result.severity in {"low", "medium", "high"}
    assert "cpu" in result.triggered_features
    assert "memory" in result.triggered_features


def test_root_cause_agent_uses_qwen_response(monkeypatch):
    observation = _make_observation(cpu=90.0, memory=85.0)
    anomaly_result = AnomalyResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        is_anomaly=True,
        severity="medium",
        score=-0.1,
        summary="Isolation Forest detected anomalous system behavior.",
        triggered_features=["cpu", "memory"],
    )

    def fake_call(self, prompt: str):
        assert "cpu" in prompt
        return {
            "likely_root_cause": "high_cpu_memory_usage",
            "confidence": 0.75,
            "evidence": ["cpu: 90.0", "memory: 85.0"],
            "explanation": "High CPU and memory explain the anomaly.",
            "recommended_next_checks": ["check running processes"],
        }

    monkeypatch.setattr(RootCauseAgent, "_call_qwen", fake_call)

    result = RootCauseAgent().diagnose(observation, anomaly_result)

    assert result.likely_root_cause == "high_cpu_memory_usage"
    assert result.confidence == 0.75
    assert result.evidence == ["cpu: 90.0", "memory: 85.0"]


def test_root_cause_agent_falls_back_when_qwen_fails(monkeypatch):
    observation = _make_observation(cpu=90.0, memory=85.0)
    anomaly_result = AnomalyResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        is_anomaly=True,
        severity="medium",
        score=-0.1,
        summary="Isolation Forest detected anomalous system behavior.",
        triggered_features=["cpu", "memory"],
    )

    def raise_error(self, prompt: str):
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(RootCauseAgent, "_call_qwen", raise_error)

    result = RootCauseAgent().diagnose(observation, anomaly_result)

    assert result.likely_root_cause == "high_cpu_memory_usage"
    assert result.confidence == 0.55
    assert any("LLM unavailable" in item for item in result.evidence)
    assert "Check running processes for CPU-heavy workloads." in result.recommended_next_checks


def test_action_agent_maps_cpu_memory_pressure_to_high_urgency():
    observation = _make_observation(cpu=90.0, memory=85.0)
    anomaly_result = AnomalyResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        is_anomaly=True,
        severity="medium",
        score=-0.1,
        summary="Isolation Forest detected anomalous system behavior.",
        triggered_features=["cpu", "memory"],
    )
    diagnosis_result = DiagnosisResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        likely_root_cause="high_cpu_memory_usage",
        confidence=0.8,
        evidence=["cpu: 90.0", "memory: 85.0"],
        explanation="CPU and memory pressure explain the anomaly.",
        recommended_next_checks=["check running processes"],
    )

    result = ActionAgent().recommend(observation, anomaly_result, diagnosis_result)

    assert result.urgency == "high"
    assert result.requires_human_approval is True
    assert "CPU and memory pressure" in result.recommendation


def test_action_agent_uses_safe_fallback_for_unknown_root_cause():
    observation = _make_observation(cpu=50.0, memory=40.0)
    anomaly_result = AnomalyResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        is_anomaly=True,
        severity="medium",
        score=-0.05,
        summary="Anomaly detected with unclear cause.",
        triggered_features=[],
    )
    diagnosis_result = DiagnosisResult(
        instance_id="i-test",
        timestamp=observation.timestamp,
        likely_root_cause="unknown",
        confidence=0.3,
        evidence=["weak evidence"],
        explanation="Cause is unclear.",
        recommended_next_checks=["inspect manually"],
    )

    result = ActionAgent().recommend(observation, anomaly_result, diagnosis_result)

    assert result.urgency == "medium"
    assert result.requires_human_approval is True
    assert result.recommendation == "Review the incident manually before applying remediation."


def test_orchestrator_builds_incident_result_from_agent_outputs():
    observation = _make_observation(cpu=90.0, memory=85.0)

    class StubAnomalyAgent:
        def detect(self, observation):
            return AnomalyResult(
                instance_id=observation.instance_id,
                timestamp=observation.timestamp,
                is_anomaly=True,
                severity="high",
                score=-0.2,
                summary="Anomaly detected.",
                triggered_features=["cpu", "memory"],
            )

    class StubRootCauseAgent:
        def diagnose(self, observation, anomaly_result):
            return DiagnosisResult(
                instance_id=observation.instance_id,
                timestamp=observation.timestamp,
                likely_root_cause="high_cpu_memory_usage",
                confidence=0.9,
                evidence=["cpu: 90.0", "memory: 85.0"],
                explanation="CPU and memory pressure explain the anomaly.",
                recommended_next_checks=["check processes"],
            )

    class StubActionAgent:
        def recommend(self, observation, anomaly_result, diagnosis_result):
            return ActionResult(
                instance_id=observation.instance_id,
                timestamp=observation.timestamp,
                urgency="high",
                recommendation="Stabilize CPU and memory pressure on the instance.",
                remediation_steps=["Inspect the busiest processes."],
                engineer_advice="Investigate the workload before restarting anything.",
                requires_human_approval=True,
            )

    result = run_incident_workflow_from_observation(
        observation,
        anomaly_agent=StubAnomalyAgent(),
        root_cause_agent=StubRootCauseAgent(),
        action_agent=StubActionAgent(),
    )

    assert result.instance_id == "i-test"
    assert result.anomaly_result.severity == "high"
    assert result.diagnosis_result.likely_root_cause == "high_cpu_memory_usage"
    assert result.action_result.urgency == "high"
