from backend.schemas.metrics import Metrics
from backend.aws.cloudwatch_collector import fetch_all_metrics_batch, fetch_single_metric
import logging


def collect_metrics(instance_id: str) -> Metrics:
    """Production — fetch all metrics in one batch call."""
    raw = fetch_all_metrics_batch(instance_id)

    def _value(name: str) -> float:
        value = raw.get(name)
        return value if value is not None else 0.0

    # EBS values are per volume — aggregate across all attached volumes
    def _sum_ebs(metric_name: str) -> float:
        return sum(
            v for k, v in raw.items()
            if k.startswith(metric_name.lower()) and v is not None
        )

    metrics = Metrics(
        instance_id = instance_id,
        # Core
        cpu=_value("cpuutilization"),
        memory=_value("mem_used_percent"),

        # GPU (optional)
        gpu_utilization=_value("gpuutilization"),
        gpu_memory_utilization=_value("gpumemoryutilization"),
        gpu_encoder_session_count=_value("gpuencoderstatssessioncount"),

        # Network
        network_in=_value("networkin"),
        network_out=_value("networkout"),
        network_packets_in=_value("networkpacketsin"),
        network_packets_out=_value("networkpacketsout"),

        # Instance store disk
        disk_read_ops=_value("diskreadops"),
        disk_write_ops=_value("diskwriteops"),
        disk_read_bytes=_value("diskreadbytes"),
        disk_write_bytes=_value("diskwritebytes"),

        # EBS (aggregated across volumes)
        volume_read_bytes=_sum_ebs("volumereadbytes"),
        volume_write_bytes=_sum_ebs("volumewritebytes"),
        volume_read_ops=_sum_ebs("volumereadops"),
        volume_write_ops=_sum_ebs("volumewriteops"),
    )

    logging.info("Metrics collected for %s: %s", instance_id, metrics.model_dump())
    return metrics


def debug_metric(instance_id: str, metric_name: str, namespace: str, stat: str = "Average"):
    """
    Debug/testing — fetch and print a single metric.

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
    print(f"[DEBUG] {namespace}/{metric_name} for {instance_id} → {value}")
    return value