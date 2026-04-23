from pydantic import BaseModel

from backend.schemas.observation import Observation
from backend.schemas.anomaly_result import AnomalyResult


class InferenceResponse(BaseModel):
    observation: Observation
    result: AnomalyResult