from __future__ import annotations

from datetime import datetime, timezone

from backend.agents.monitoring_agent.monitoring_utils import (
    build_metrics,
    compute_data_quality,
    detect_missing_metrics,
    summarize_logs,
)
from backend.aws.cloudwatch_collector import fetch_all_metrics_batch
from backend.aws.log_collector import fetch_logs
from backend.config.settings import AWS_REGION, INSTANCE_ID, LOG_GROUP_NAME
from backend.schemas.log_event import LogEvent
from backend.schemas.observation import Observation, SourceMetadata


class MonitoringAgent:
    """Deterministic AWS monitoring layer for the current system state."""

    def __init__(
        self,
        *,
        instance_id: str = INSTANCE_ID,
        aws_region: str = AWS_REGION,
        log_group_name: str = LOG_GROUP_NAME,
        metrics_window_minutes: int = 10,
        logs_window_minutes: int = 60,
    ) -> None:
        self.instance_id = instance_id
        self.aws_region = aws_region
        self.log_group_name = log_group_name
        self.metrics_window_minutes = metrics_window_minutes
        self.logs_window_minutes = logs_window_minutes

    def fetch_metrics(self) -> dict[str, float | None]:
        return fetch_all_metrics_batch(
            instance_id=self.instance_id,
            minutes=self.metrics_window_minutes,
        )

    def fetch_logs(self) -> list[LogEvent]:
        return fetch_logs(
            instance_id=self.instance_id,
            log_group_name=self.log_group_name,
            minutes=self.logs_window_minutes,
        )

    def package_observation(
        self,
        *,
        raw_metrics: dict[str, float | None],
        logs: list[LogEvent],
        observation_time: datetime | None = None,
    ) -> Observation:
        observation_time = observation_time or datetime.now(timezone.utc)
        metrics = build_metrics(self.instance_id, raw_metrics)
        missing_metrics = detect_missing_metrics(raw_metrics)
        data_quality = compute_data_quality(
            observation_time=observation_time,
            metrics_timestamp=metrics.timestamp,
            logs=logs,
            missing_metrics=missing_metrics,
        )

        return Observation(
            instance_id=self.instance_id,
            timestamp=observation_time,
            metrics=metrics,
            log_summary=summarize_logs(logs),
            raw_log_count=len(logs),
            data_quality=data_quality,
            missing_metrics=missing_metrics,
            source_metadata=SourceMetadata(
                aws_region=self.aws_region,
                log_group_name=self.log_group_name,
                log_stream_name=self.instance_id,
                metrics_window_minutes=self.metrics_window_minutes,
                logs_window_minutes=self.logs_window_minutes,
                namespaces=["AWS/EC2", "AWS/EBS", "CWAgent", "CloudWatchLogs"],
            ),
            is_trustworthy=data_quality.is_fresh and data_quality.completeness_score >= 0.7,
        )

    def collect(self) -> tuple[Observation, list[LogEvent]]:
        observation_time = datetime.now(timezone.utc)
        raw_metrics = self.fetch_metrics()
        logs = self.fetch_logs()
        observation = self.package_observation(
            raw_metrics=raw_metrics,
            logs=logs,
            observation_time=observation_time,
        )
        return observation, logs

    def collect_observation(self) -> Observation:
        observation, _ = self.collect()
        return observation


def collect_observation(
    *,
    instance_id: str = INSTANCE_ID,
    aws_region: str = AWS_REGION,
    log_group_name: str = LOG_GROUP_NAME,
    metrics_window_minutes: int = 10,
    logs_window_minutes: int = 60,
) -> Observation:
    agent = MonitoringAgent(
        instance_id=instance_id,
        aws_region=aws_region,
        log_group_name=log_group_name,
        metrics_window_minutes=metrics_window_minutes,
        logs_window_minutes=logs_window_minutes,
    )
    return agent.collect_observation()
