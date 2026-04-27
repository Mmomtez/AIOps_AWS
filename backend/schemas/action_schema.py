from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ActionResult(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the action plan was generated",
    )
    urgency: str = Field(default="low", description="Operational urgency level")
    recommendation: str = Field(
        default="Continue monitoring the instance.",
        description="Top-level remediation recommendation",
    )
    remediation_steps: list[str] = Field(
        default_factory=list,
        description="Concrete remediation or verification steps",
    )
    engineer_advice: str = Field(
        default="No additional engineer guidance available.",
        description="Engineer-facing operational advice",
    )
    requires_human_approval: bool = Field(
        default=False,
        description="Whether the proposed action should be human-approved before execution",
    )
