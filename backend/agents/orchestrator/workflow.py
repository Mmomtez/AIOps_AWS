from __future__ import annotations

from backend.agents.action_agent.remediation_engine import ActionAgent
from backend.agents.anomaly_agent.anomaly_detector import AnomalyAgent
from backend.agents.monitoring_agent.monitoring_agent import MonitoringAgent
from backend.agents.root_cause_agent.root_cause_agent import RootCauseAgent
from backend.schemas.incident_schema import IncidentResult
from backend.schemas.observation import Observation


def run_incident_workflow(
    *,
    monitoring_agent: MonitoringAgent | None = None,
    anomaly_agent: AnomalyAgent | None = None,
    root_cause_agent: RootCauseAgent | None = None,
    action_agent: ActionAgent | None = None,
) -> IncidentResult:
    monitoring_agent = monitoring_agent or MonitoringAgent()
    observation = monitoring_agent.collect_observation()

    return run_incident_workflow_from_observation(
        observation,
        anomaly_agent=anomaly_agent,
        root_cause_agent=root_cause_agent,
        action_agent=action_agent,
    )


def run_incident_workflow_from_observation(
    observation: Observation,
    *,
    anomaly_agent: AnomalyAgent | None = None,
    root_cause_agent: RootCauseAgent | None = None,
    action_agent: ActionAgent | None = None,
) -> IncidentResult:
    anomaly_agent = anomaly_agent or AnomalyAgent()
    root_cause_agent = root_cause_agent or RootCauseAgent()
    action_agent = action_agent or ActionAgent()

    anomaly_result = anomaly_agent.detect(observation)
    diagnosis_result = root_cause_agent.diagnose(observation, anomaly_result)
    action_result = action_agent.recommend(observation, anomaly_result, diagnosis_result)

    return IncidentResult(
        instance_id=observation.instance_id,
        observation=observation,
        anomaly_result=anomaly_result,
        diagnosis_result=diagnosis_result,
        action_result=action_result,
    )
