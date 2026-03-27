# Data ingestion pipeline
from aws.collector_service import collect_metrics
from aws.log_collector import fetch_logs
from aws.storage import save_metrics, save_logs
from aws.s3_storage import upload_metrics_to_s3, upload_logs_to_s3

from config.settings import INSTANCE_ID, S3_BUCKET_NAME


LOG_GROUP_NAME = "ec2AGENTLOGS"


def run_ingestion_pipeline():
    # ── Metrics ───────────────────────────────────────────────
    metrics = collect_metrics(INSTANCE_ID)
    print("Collected metrics:", metrics)

    save_metrics(metrics)

    metrics_s3_key = upload_metrics_to_s3(
        metrics,
        bucket_name=S3_BUCKET_NAME,
    )

    print(f"Metrics uploaded to S3: s3://{S3_BUCKET_NAME}/{metrics_s3_key}")

    # ── Logs ──────────────────────────────────────────────────
    logs = fetch_logs(
        instance_id=INSTANCE_ID,
        log_group_name=LOG_GROUP_NAME,
        minutes=60 # wider window
    )

    print(f"Fetched {len(logs)} logs")

    save_logs(logs)

    logs_s3_key = upload_logs_to_s3(
        logs,
        bucket_name=S3_BUCKET_NAME,
        instance_id=INSTANCE_ID,
    )

    if logs_s3_key:
        print(f"Logs uploaded to S3: s3://{S3_BUCKET_NAME}/{logs_s3_key}")

    return {
        "metrics": metrics,
        "logs": logs
    }