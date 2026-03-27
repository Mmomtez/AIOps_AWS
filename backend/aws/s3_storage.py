# S3 storage helper
import json
import logging
from typing import List


import boto3

from config.settings import AWS_REGION
from schemas.metrics import Metrics
from schemas.log_event import LogEvent




s3_client = boto3.client("s3", region_name=AWS_REGION)


def save_json_to_s3(data: dict, bucket_name: str, key: str) -> None:
    """
    Upload any JSON-serializable dictionary to S3.
    """
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=json.dumps(data, indent=2),
            ContentType="application/json",
        )
        logging.info("JSON uploaded to s3://%s/%s", bucket_name, key)
    except Exception as e:
        logging.error("Failed to upload JSON to s3://%s/%s: %s", bucket_name, key, e)
        raise


def upload_metrics_to_s3(metrics: Metrics, bucket_name: str, prefix: str = "metrics") -> str:
    """
    Upload a Metrics object to S3 using a structured key.

    Example key:
        metrics/i-01853187eb3bc8554/2026-03-25T18-51-45.679125+00-00.json
    """
    safe_timestamp = metrics.timestamp.isoformat().replace(":", "-")
    key = f"{prefix}/{metrics.instance_id}/{safe_timestamp}.json"

    save_json_to_s3(
        data=metrics.model_dump(mode="json"),
        bucket_name=bucket_name,
        key=key,
    )

    return key


def upload_logs_to_s3(
    logs: List[LogEvent],
    bucket_name: str,
    instance_id: str,
    prefix: str = "logs",
):
    if not logs:
        return None

    # use timestamp of first log for filename
    timestamp = logs[0].timestamp.isoformat().replace(":", "-")

    key = f"{prefix}/{instance_id}/{timestamp}.json"

    save_json_to_s3(
        data=[log.model_dump(mode="json") for log in logs],
        bucket_name=bucket_name,
        key=key,
    )

    return key

