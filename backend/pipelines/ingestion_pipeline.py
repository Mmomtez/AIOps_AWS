# Data ingestion pipeline
from backend.agents.monitoring_agent.monitoring_agent import MonitoringAgent
from backend.aws.s3_storage import upload_logs_to_s3, upload_metrics_to_s3
from backend.aws.storage import save_logs, save_metrics, save_observation
from backend.config.settings import INSTANCE_ID, LOG_GROUP_NAME, S3_BUCKET_NAME
from backend.schemas.observation import Observation


def run_ingestion_pipeline() -> Observation:
    monitoring_agent = MonitoringAgent(
        instance_id=INSTANCE_ID,
        log_group_name=LOG_GROUP_NAME,
    )
    observation, logs = monitoring_agent.collect()
    metrics = observation.metrics

    print("Collected metrics:", metrics)
    save_metrics(metrics)

    metrics_s3_key = upload_metrics_to_s3(
        metrics,
        bucket_name=S3_BUCKET_NAME,
    )
    observation.source_metadata.metrics_s3_key = metrics_s3_key
    print(f"Metrics uploaded to S3: s3://{S3_BUCKET_NAME}/{metrics_s3_key}")

    print(f"Fetched {len(logs)} logs")
    save_logs(logs)

    logs_s3_key = upload_logs_to_s3(
        logs,
        bucket_name=S3_BUCKET_NAME,
        instance_id=INSTANCE_ID,
    )
    observation.source_metadata.logs_s3_key = logs_s3_key

    if logs_s3_key:
        print(f"Logs uploaded to S3: s3://{S3_BUCKET_NAME}/{logs_s3_key}")

    observation_path = save_observation(observation)
    print(f"Observation saved locally: {observation_path}")

    return observation
