from __future__ import annotations

from backend.schemas.action_schema import ActionResult
from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.diagnosis_result import DiagnosisResult
from backend.schemas.observation import Observation


ACTION_PLANS = {
    "high_cpu_memory_usage": {
        "urgency": "high",
        "recommendation": "Stabilize CPU and memory pressure on the instance.",
        "remediation_steps": [
            "Inspect the busiest processes and worker pools on the instance.",
            "Reduce load, scale capacity, or restart stuck workers during a safe window.",
            "Review recent deployments or workload spikes that correlate with the anomaly.",
        ],
        "engineer_advice": (
            "Treat combined CPU and memory pressure as a capacity or runaway-process incident "
            "until proven otherwise."
        ),
        "requires_human_approval": True,
    },
    "high_cpu_utilization": {
        "urgency": "medium",
        "recommendation": "Investigate and reduce CPU saturation.",
        "remediation_steps": [
            "Inspect top CPU-consuming processes.",
            "Check for recent jobs, deployments, or traffic spikes.",
            "Scale out or rebalance workload if sustained saturation continues.",
        ],
        "engineer_advice": "Confirm whether the CPU spike is expected workload or abnormal behavior.",
        "requires_human_approval": False,
    },
    "high_memory_utilization": {
        "urgency": "high",
        "recommendation": "Investigate memory pressure and recover headroom.",
        "remediation_steps": [
            "Identify memory-heavy processes or containers.",
            "Check for leaks, queue buildup, or stuck workers.",
            "Restart unhealthy components during a safe maintenance window if needed.",
        ],
        "engineer_advice": "Prioritize leak detection and OOM prevention before the host destabilizes.",
        "requires_human_approval": True,
    },
    "gpu_saturation": {
        "urgency": "medium",
        "recommendation": "Inspect GPU workload saturation.",
        "remediation_steps": [
            "Review active GPU inference or training jobs.",
            "Check GPU memory allocation and queue depth.",
            "Reschedule or distribute GPU-intensive workloads if saturation persists.",
        ],
        "engineer_advice": "Correlate GPU pressure with model-serving or training demand.",
        "requires_human_approval": False,
    },
    "network_traffic_spike": {
        "urgency": "medium",
        "recommendation": "Validate whether the traffic spike is expected and protect the service if not.",
        "remediation_steps": [
            "Check recent request volume and inbound traffic sources.",
            "Inspect load balancer, API gateway, or service logs for bursts.",
            "Apply rate limiting or scaling if the spike is sustained and legitimate.",
        ],
        "engineer_advice": "Differentiate organic growth from abusive or misrouted traffic before acting.",
        "requires_human_approval": False,
    },
    "disk_io_pressure": {
        "urgency": "medium",
        "recommendation": "Investigate elevated disk and EBS I/O activity.",
        "remediation_steps": [
            "Identify disk-heavy workloads or batch jobs.",
            "Review database, log, or cache write amplification.",
            "Check EBS throughput and IOPS limits against current demand.",
        ],
        "engineer_advice": "Focus on the application component generating sustained write or read pressure.",
        "requires_human_approval": False,
    },
    "application_errors": {
        "urgency": "high",
        "recommendation": "Triage application failures before attempting automated remediation.",
        "remediation_steps": [
            "Inspect recent error logs and stack traces.",
            "Correlate failing endpoints or jobs with the anomaly timestamp.",
            "Roll back or isolate the affected service if a recent change is implicated.",
        ],
        "engineer_advice": "Use logs first; automated host-level actions may mask the application issue.",
        "requires_human_approval": True,
    },
    "unknown": {
        "urgency": "medium",
        "recommendation": "Review the incident manually before applying remediation.",
        "remediation_steps": [
            "Inspect the anomaly summary and diagnosis evidence.",
            "Validate whether metrics and logs tell a consistent story.",
            "Escalate to an engineer for manual triage before changing the system.",
        ],
        "engineer_advice": "Avoid aggressive remediation when the root cause remains unclear.",
        "requires_human_approval": True,
    },
    "root_cause_analysis_failed": {
        "urgency": "medium",
        "recommendation": "Verify the diagnosis path and review the incident manually.",
        "remediation_steps": [
            "Confirm that the root cause agent and Ollama are healthy.",
            "Inspect anomaly evidence and triggered features directly.",
            "Escalate for manual triage before taking disruptive action.",
        ],
        "engineer_advice": "Treat this as a tooling degradation and avoid automated remediation.",
        "requires_human_approval": True,
    },
    "normal_operation": {
        "urgency": "low",
        "recommendation": "Continue monitoring the instance.",
        "remediation_steps": [
            "No immediate remediation is required.",
            "Keep observing the instance for repeated anomalies or log errors.",
        ],
        "engineer_advice": "Preserve the current state and watch for recurrence.",
        "requires_human_approval": False,
    },
}


class ActionAgent:
    def recommend(
        self,
        observation: Observation,
        anomaly_result: AnomalyResult,
        diagnosis_result: DiagnosisResult,
    ) -> ActionResult:
        plan = self._resolve_plan(anomaly_result, diagnosis_result)
        urgency = self._adjust_urgency(plan["urgency"], anomaly_result.severity)
        remediation_steps = list(plan["remediation_steps"])
        engineer_advice = plan["engineer_advice"]
        requires_human_approval = bool(plan["requires_human_approval"])

        if not observation.is_trustworthy:
            remediation_steps.insert(0, "Validate telemetry quality before applying disruptive remediation.")
            engineer_advice += " Telemetry quality is limited, so verify the observation first."
            requires_human_approval = True

        return ActionResult(
            instance_id=observation.instance_id,
            timestamp=observation.timestamp,
            urgency=urgency,
            recommendation=plan["recommendation"],
            remediation_steps=remediation_steps,
            engineer_advice=engineer_advice,
            requires_human_approval=requires_human_approval or urgency == "high",
        )

    def _resolve_plan(
        self,
        anomaly_result: AnomalyResult,
        diagnosis_result: DiagnosisResult,
    ) -> dict[str, object]:
        if not anomaly_result.is_anomaly:
            return ACTION_PLANS["normal_operation"]

        root_cause = diagnosis_result.likely_root_cause or "unknown"
        return ACTION_PLANS.get(root_cause, ACTION_PLANS["unknown"])

    def _adjust_urgency(self, base_urgency: str, anomaly_severity: str) -> str:
        if anomaly_severity == "high" and base_urgency == "medium":
            return "high"
        return base_urgency


def recommend_action(
    observation: Observation,
    anomaly_result: AnomalyResult,
    diagnosis_result: DiagnosisResult,
) -> ActionResult:
    return ActionAgent().recommend(observation, anomaly_result, diagnosis_result)
