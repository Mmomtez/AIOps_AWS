import logging

from backend.agents.monitoring_agent.monitoring_utils import build_metrics
from backend.aws.cloudwatch_collector import fetch_all_metrics_batch, fetch_single_metric
from backend.schemas.metrics import Metrics


def collect_metrics(instance_id: str) -> Metrics:
    """Production: fetch all metrics in one batch call."""
    raw = fetch_all_metrics_batch(instance_id)
    metrics = build_metrics(instance_id, raw)

    logging.info("Metrics collected for %s: %s", instance_id, metrics.model_dump())
    return metrics


def debug_metric(instance_id: str, metric_name: str, namespace: str, stat: str = "Average"):
    """
    Debug/testing: fetch and print a single metric.

    Best for:
        debug_metric("i-0abc123", "CPUUtilization", "AWS/EC2")
        debug_metric("i-0abc123", "mem_used_percent", "CWAgent")
        debug_metric("i-0abc123", "NetworkIn", "AWS/EC2", stat="Sum")
    """
    dimensions = [{"Name": "InstanceId", "Value": instance_id}]
    value = fetch_single_metric(
        metric_name=metric_name,
        namespace=namespace,
        dimensions=dimensions,
        stat=stat,
    )
    print(f"[DEBUG] {namespace}/{metric_name} for {instance_id} -> {value}")
    return value
