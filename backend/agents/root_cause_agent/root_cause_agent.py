from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.diagnosis_result import DiagnosisResult
from backend.schemas.observation import Observation


class RootCauseAgent:
    def __init__(
        self,
        model_name: str | None = None,
        ollama_base_url: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.model_name = model_name or os.getenv("ROOT_CAUSE_MODEL", "qwen2.5:7b")
        self.ollama_base_url = (
            ollama_base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def diagnose(
        self,
        observation: Observation,
        anomaly_result: AnomalyResult,
    ) -> DiagnosisResult:
        if not anomaly_result.is_anomaly:
            return DiagnosisResult(
                instance_id=observation.instance_id,
                timestamp=observation.timestamp,
                likely_root_cause="normal_operation",
                confidence=0.8,
                evidence=[anomaly_result.summary],
                explanation="No abnormal system behavior was detected.",
                recommended_next_checks=[],
            )

        try:
            response = self._call_qwen(self._build_prompt(observation, anomaly_result))
        except Exception as exc:
            return self._fallback_diagnosis(observation, anomaly_result, exc)

        return DiagnosisResult(
            instance_id=observation.instance_id,
            timestamp=observation.timestamp,
            likely_root_cause=str(response.get("likely_root_cause", "unknown")),
            confidence=self._confidence(response.get("confidence")),
            evidence=self._string_list(response.get("evidence")),
            explanation=str(response.get("explanation", "No explanation provided.")),
            recommended_next_checks=self._string_list(
                response.get("recommended_next_checks")
            ),
        )

    def _build_prompt(
        self,
        observation: Observation,
        anomaly_result: AnomalyResult,
    ) -> str:
        payload = {
            "instance_id": observation.instance_id,
            "timestamp": observation.timestamp,
            "metrics": observation.metrics.model_dump(),
            "log_summary": observation.log_summary.model_dump(),
            "data_quality": observation.data_quality.model_dump(),
            "missing_metrics": observation.missing_metrics,
            "is_trustworthy": observation.is_trustworthy,
            "anomaly_result": anomaly_result.model_dump(),
        }

        return f"""
You are a root cause analysis agent for an AWS AIOps system.

Return ONLY valid JSON with this shape:
{{
  "likely_root_cause": "short_snake_case_category",
  "confidence": 0.0,
  "evidence": ["specific metric/log/anomaly signal"],
  "explanation": "clear engineer-facing explanation",
  "recommended_next_checks": ["specific operational check"]
}}

Rules:
- Use only the input data.
- Do not invent missing logs, deployments, services, or AWS resources.
- confidence must be between 0 and 1.
- Evidence must cite concrete input values.
- If data quality is weak, lower confidence.

Input:
{json.dumps(payload, default=str, indent=2)}
""".strip()

    def _call_qwen(self, prompt: str) -> dict[str, Any]:
        request = Request(
            f"{self.ollama_base_url}/api/generate",
            data=json.dumps(
                {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as exc:
            raise RuntimeError(f"Could not reach Ollama at {self.ollama_base_url}") from exc

        raw_response = str(payload.get("response", "")).strip()
        if not raw_response:
            raise ValueError("Qwen returned an empty response.")

        parsed = json.loads(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError("Qwen response was not a JSON object.")

        return parsed

    def _fallback_diagnosis(
        self,
        observation: Observation,
        anomaly_result: AnomalyResult,
        error: Exception,
    ) -> DiagnosisResult:
        triggered_features = anomaly_result.triggered_features
        evidence = [anomaly_result.summary]

        if triggered_features:
            evidence.append(f"Triggered features: {', '.join(triggered_features)}.")
        if observation.missing_metrics:
            evidence.append(f"Missing metrics: {', '.join(observation.missing_metrics)}.")
        if not observation.data_quality.has_logs:
            evidence.append("No logs were available for LLM-assisted diagnosis.")
        if not observation.is_trustworthy:
            evidence.append("Observation quality is limited.")
        evidence.append(f"LLM unavailable: {error}")

        return DiagnosisResult(
            instance_id=observation.instance_id,
            timestamp=observation.timestamp,
            likely_root_cause=self._fallback_root_cause(triggered_features),
            confidence=0.55 if observation.is_trustworthy else 0.35,
            evidence=evidence,
            explanation=(
                "Root cause agent fell back to deterministic diagnosis because "
                "Ollama/Qwen was unavailable or returned invalid output."
            ),
            recommended_next_checks=self._fallback_next_checks(triggered_features),
        )

    def _fallback_root_cause(self, triggered_features: list[str]) -> str:
        feature_set = set(triggered_features)

        if {"cpu", "memory"}.issubset(feature_set):
            return "high_cpu_memory_usage"
        if "cpu" in feature_set:
            return "high_cpu_utilization"
        if "memory" in feature_set:
            return "high_memory_utilization"
        if "gpu_utilization" in feature_set or "gpu_memory_utilization" in feature_set:
            return "gpu_saturation"
        if "network_in" in feature_set or "network_out" in feature_set:
            return "network_traffic_spike"
        if "volume_write_bytes" in feature_set:
            return "disk_io_pressure"

        return "unknown"

    def _fallback_next_checks(self, triggered_features: list[str]) -> list[str]:
        feature_set = set(triggered_features)
        checks: list[str] = []

        if "cpu" in feature_set:
            checks.append("Check running processes for CPU-heavy workloads.")
        if "memory" in feature_set:
            checks.append("Check for memory-heavy workers or leaks.")
        if "gpu_utilization" in feature_set or "gpu_memory_utilization" in feature_set:
            checks.append("Inspect active GPU jobs and memory allocation.")
        if "network_in" in feature_set or "network_out" in feature_set:
            checks.append("Review traffic sources and recent request volume.")
        if "volume_write_bytes" in feature_set:
            checks.append("Inspect disk-heavy jobs and recent write throughput.")

        if not checks:
            checks.append("Inspect the raw observation and anomaly summary manually.")

        return checks

    def _confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 0.5

        return max(0.0, min(confidence, 1.0))

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        return [str(item) for item in value if str(item).strip()]


def diagnose_root_cause(
    observation: Observation,
    anomaly_result: AnomalyResult,
) -> DiagnosisResult:
    return RootCauseAgent().diagnose(observation, anomaly_result)
