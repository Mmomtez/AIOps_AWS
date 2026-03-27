# Entry point for running the system
from dotenv import load_dotenv
import os
from aws.collector_service import collect_metrics
from aws.s3_storage import upload_logs_to_s3, upload_metrics_to_s3
from aws.storage import save_logs, save_metrics
import logging
from config.settings import INSTANCE_ID, LOG_GROUP_NAME, S3_BUCKET_NAME
from aws.log_collector import fetch_logs

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

if __name__ == "__main__":
    metrics = collect_metrics(INSTANCE_ID)

    print("Collected:", metrics)
    save_metrics(metrics)
    s3_key = upload_metrics_to_s3(metrics, bucket_name=S3_BUCKET_NAME)
    if s3_key:
        print(f"Uploaded to S3: s3://{S3_BUCKET_NAME}/{s3_key}")

    logs = fetch_logs(
      instance_id=INSTANCE_ID,
      log_group_name=LOG_GROUP_NAME,
      minutes=120,
    )
    logs = logs or []
    print(f"Fetched {len(logs)} logs")
    save_logs(logs)
    s3_key = upload_logs_to_s3(
    logs,
    bucket_name=S3_BUCKET_NAME,
    instance_id=INSTANCE_ID,
      )

    if s3_key:
        print(f"Logs uploaded to S3: s3://{S3_BUCKET_NAME}/{s3_key}")


