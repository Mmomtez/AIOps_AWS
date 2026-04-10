from datetime import datetime
from pydantic import BaseModel

from backend.schemas.metrics import Metrics


class LogSummary(BaseModel):
    error_count: int = 0
    warning_count: int = 0
    keywords: list[str] = []


class Observation(BaseModel):
    instance_id: str
    timestamp: datetime
    metrics: Metrics
    raw_log_count: int
    log_summary: LogSummary