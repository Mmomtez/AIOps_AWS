from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.schemas.action_schema import ActionResult
from backend.schemas.anomaly_result import AnomalyResult
from backend.schemas.diagnosis_result import DiagnosisResult
from backend.schemas.observation import Observation


class IncidentResult(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the incident report was assembled",
    )
    observation: Observation
    anomaly_result: AnomalyResult
    diagnosis_result: DiagnosisResult
    action_result: ActionResult
