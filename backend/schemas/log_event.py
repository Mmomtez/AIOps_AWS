from datetime import datetime, timezone
from pydantic import BaseModel, Field


class LogEvent(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the log event",
    )
    log_group: str = Field(..., description="CloudWatch Logs group name")
    log_stream: str = Field(..., description="CloudWatch Logs stream name")
    message: str = Field(..., description="Raw log message")