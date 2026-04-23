import logging
from datetime import datetime, timezone, timedelta

import boto3

from backend.config.settings import AWS_REGION
from backend.schemas.log_event import LogEvent


logs_client = boto3.client("logs", region_name=AWS_REGION)


def fetch_logs(
    instance_id: str,
    log_group_name: str,
    minutes: int = 10,
) -> list[LogEvent]:
    """
    Fetch recent logs from CloudWatch Logs for a specific EC2 instance.

    Assumes:
        log_stream_name = instance_id
    """
    log_stream_name = instance_id
    start_time = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)

    try:
        response = logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_name,
            startTime=start_time,
            startFromHead=False,
        )

        events = response.get("events", [])

        logs = []
        for event in events:
            logs.append(
                LogEvent(
                    instance_id=instance_id,
                    timestamp=datetime.fromtimestamp(event["timestamp"] / 1000, tz=timezone.utc),
                    log_group=log_group_name,
                    log_stream=log_stream_name,
                    message=event["message"],
                )
            )

        logging.info("Fetched %s log events for %s", len(logs), instance_id)
        return logs

    except logs_client.exceptions.ResourceNotFoundException:
        logging.warning(
            "Log group or stream not found: %s / %s",
            log_group_name,
            log_stream_name,
        )
        return []

    except Exception as e:
        logging.error("Failed to fetch logs for %s: %s", instance_id, e)
        return []