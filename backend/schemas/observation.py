from datetime import datetime

from pydantic import BaseModel, Field

from backend.schemas.metrics import Metrics


class LogSummary(BaseModel):
    error_count: int = 0
    warning_count: int = 0
    keywords: list[str] = Field(default_factory=list)
    sample_messages: list[str] = Field(default_factory=list)


class DataQuality(BaseModel):
    freshness_seconds: float = 0.0
    metrics_age_seconds: float = 0.0
    logs_age_seconds: float | None = None
    completeness_score: float = 0.0
    missing_data_points: int = 0
    has_logs: bool = False
    is_fresh: bool = False


class SourceMetadata(BaseModel):
    aws_region: str
    log_group_name: str
    log_stream_name: str
    metrics_window_minutes: int
    logs_window_minutes: int
    namespaces: list[str] = Field(default_factory=list)
    metrics_s3_key: str | None = None
    logs_s3_key: str | None = None


class Observation(BaseModel):
    instance_id: str
    timestamp: datetime
    metrics: Metrics
    log_summary: LogSummary
    raw_log_count: int
    data_quality: DataQuality
    missing_metrics: list[str] = Field(default_factory=list)
    source_metadata: SourceMetadata
    is_trustworthy: bool = False
