from schemas.metrics import Metrics
from aws.cloudwatch_collector import fetch_cpu_utilization, fetch_memory_utilization
import random
import logging


def collect_metrics(instance_id: str) -> Metrics:
    cpu = fetch_cpu_utilization(instance_id)

    # simulate other metrics for now
    memory = fetch_memory_utilization(instance_id) 
    metrics = Metrics(
        cpu=cpu if cpu else 0,
        memory=memory if memory else 0,
    )

    logging.info(f"Metrics collected for {instance_id}: {metrics.model_dump()}")

    return metrics