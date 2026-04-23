# Data ingestion pipeline
from backend.aws.collector_service import collect_metrics
from backend.aws.log_collector import fetch_logs
from backend.aws.storage import save_metrics, save_logs, save_observation
from backend.aws.s3_storage import upload_metrics_to_s3, upload_logs_to_s3
from backend.schemas.observation import Observation, LogSummary

from backend.config.settings import INSTANCE_ID, S3_BUCKET_NAME, LOG_GROUP_NAME


def summarize_logs(logs: list[dict]) -> dict:
    error_count = 0
    warning_count = 0
    keywords_found = set()

    tracked_keywords = ["error", "exception", "timeout", "failed", "refused", "killed"]

    for log in logs:
        message = log.get("message", "").lower()

        if "error" in message:
            error_count += 1

        if "warning" in message:
            warning_count += 1

        for keyword in tracked_keywords:
            if keyword in message:
                keywords_found.add(keyword)

    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "keywords": sorted(list(keywords_found)),
    }


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
        minutes=60,
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

    # Log summary
    log_summary = summarize_logs(logs)

    # Final observation object
    observation = Observation(
        instance_id=INSTANCE_ID,
        timestamp=metrics.timestamp,
        metrics=metrics,
        raw_log_count=len(logs),
        log_summary=LogSummary(**log_summary),
    )

    observation_path = save_observation(observation)
    print(f"Observation saved locally: {observation_path}")

    return observation