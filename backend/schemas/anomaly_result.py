from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AnomalyResult(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when anomaly detection was performed",
    )
    is_anomaly: bool = Field(..., description="Whether an anomaly was detected")
    severity: str = Field(default="low", description="Anomaly severity level")
    score: float = Field(default=0.0, description="Anomaly score or confidence value")
    summary: str = Field(default="", description="Human-readable anomaly summary")
    triggered_features: list[str] = Field(
        default_factory=list,
        description="Metrics that triggered the anomaly logic",
    )