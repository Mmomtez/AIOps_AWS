from datetime import datetime, timezone

from pydantic import BaseModel, Field


class DiagnosisResult(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when root cause analysis was performed",
    )
    likely_root_cause: str = Field(default="unknown")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    explanation: str = Field(default="No diagnosis available.")
    recommended_next_checks: list[str] = Field(default_factory=list)
