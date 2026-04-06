import logging
from datetime import datetime, timezone, timedelta

import boto3

from backend.config.settings import AWS_REGION

cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
ec2_client = boto3.client("ec2", region_name=AWS_REGION)


# ── constants ──────────────────────────────────────────────────────────────────

EC2_METRICS = {
    "CPUUtilization": "Average",
    "NetworkIn": "Sum",
    "NetworkOut": "Sum",
    "NetworkPacketsIn": "Sum",
    "NetworkPacketsOut": "Sum",
    "DiskReadOps": "Sum",
    "DiskWriteOps": "Sum",
    "DiskReadBytes": "Sum",
    "DiskWriteBytes": "Sum",
}

# Required CWAgent metrics for your current setup
CWAGENT_METRICS = {
    "mem_used_percent": "Average",
}

# Optional CWAgent metrics: skip if not available
OPTIONAL_CWAGENT_METRICS = {
    "GPUUtilization": "Average",
    "GPUMemoryUtilization": "Average",
    "GPUEncoderStatsSessionCount": "Average",
}

EBS_METRICS = {
    "VolumeReadBytes": "Sum",
    "VolumeWriteBytes": "Sum",
    "VolumeReadOps": "Sum",
    "VolumeWriteOps": "Sum",
}


# ── caches ─────────────────────────────────────────────────────────────────────

CWAGENT_DIMENSIONS_CACHE = {}
VOLUME_IDS_CACHE = {}

CACHE_TTL = timedelta(minutes=15)
CACHE_LAST_REFRESH = datetime.now(timezone.utc)


# ── cache helpers ──────────────────────────────────────────────────────────────

def clear_metric_caches() -> None:
    """Clear in-memory discovery caches."""
    global CACHE_LAST_REFRESH

    CWAGENT_DIMENSIONS_CACHE.clear()
    VOLUME_IDS_CACHE.clear()
    CACHE_LAST_REFRESH = datetime.now(timezone.utc)
    logging.info("Metric caches cleared.")


def _refresh_caches_if_needed() -> None:
    """Clear caches automatically when TTL expires."""
    global CACHE_LAST_REFRESH

    now = datetime.now(timezone.utc)
    if now - CACHE_LAST_REFRESH >= CACHE_TTL:
        clear_metric_caches()


# ── discovery helpers ──────────────────────────────────────────────────────────

def _discover_cwagent_metrics(instance_id: str) -> dict:
    """
    Discover available CWAgent metrics and their dimensions for this instance.
    Cached per instance_id.

    Returns:
        {
            "mem_used_percent": [...dimensions...],
            "GPUUtilization": [...dimensions...],
            ...
        }
    """
    if instance_id in CWAGENT_DIMENSIONS_CACHE:
        return CWAGENT_DIMENSIONS_CACHE[instance_id]

    discovered = {}
    all_cwagent_metrics = {}
    all_cwagent_metrics.update(CWAGENT_METRICS)
    all_cwagent_metrics.update(OPTIONAL_CWAGENT_METRICS)

    for metric_name in all_cwagent_metrics.keys():
        try:
            response = cloudwatch.list_metrics(
                Namespace="CWAgent",
                MetricName=metric_name,
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
            )
            metrics = response.get("Metrics", [])

            if metrics:
                discovered[metric_name] = metrics[0]["Dimensions"]
            else:
                if metric_name in CWAGENT_METRICS:
                    logging.warning(
                        "Required CWAgent metric not available for %s: %s",
                        instance_id,
                        metric_name,
                    )
                else:
                    logging.info(
                        "Optional CWAgent metric not available for %s: %s",
                        instance_id,
                        metric_name,
                    )

        except Exception as e:
            logging.warning(
                "Failed discovering CWAgent metric %s for %s: %s",
                metric_name,
                instance_id,
                e,
            )

    CWAGENT_DIMENSIONS_CACHE[instance_id] = discovered
    return discovered


def _resolve_volume_ids(instance_id: str) -> list[str]:
    """Return cached list of EBS volume IDs attached to the instance."""
    if instance_id in VOLUME_IDS_CACHE:
        return VOLUME_IDS_CACHE[instance_id]

    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        volume_ids = []

        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                for mapping in instance.get("BlockDeviceMappings", []):
                    ebs = mapping.get("Ebs")
                    if ebs and "VolumeId" in ebs:
                        volume_ids.append(ebs["VolumeId"])

        VOLUME_IDS_CACHE[instance_id] = volume_ids
        return volume_ids

    except Exception as e:
        logging.warning("Failed to resolve volume IDs for %s: %s", instance_id, e)
        return []


def _parse_results(response: dict) -> dict:
    """Extract latest value from each MetricDataResult."""
    results = {}

    for result in response.get("MetricDataResults", []):
        result_id = result.get("Id")
        values = result.get("Values", [])
        timestamps = result.get("Timestamps", [])

        if not result_id:
            continue

        if not values:
            results[result_id] = None
            continue

        if timestamps and len(values) == len(timestamps):
            latest_idx = max(range(len(timestamps)), key=lambda i: timestamps[i])
            results[result_id] = values[latest_idx]
        else:
            results[result_id] = values[-1]

    return results


# ── 1. generic single metric (for testing/debugging) ──────────────────────────

def fetch_single_metric(
    metric_name: str,
    namespace: str,
    dimensions: list,
    stat: str = "Average",
    minutes: int = 10,
):
    """
    Fetch any single CloudWatch metric. Use this for testing/debugging.

    Example:
        fetch_single_metric(
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            dimensions=[{"Name": "InstanceId", "Value": "i-0abc123"}],
            stat="Average",
        )
    """
    try:
        now = datetime.now(timezone.utc)
        response = cloudwatch.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=now - timedelta(minutes=minutes),
            EndTime=now,
            Period=300,
            Statistics=[stat],
        )

        datapoints = response.get("Datapoints", [])
        if not datapoints:
            logging.warning("[DEBUG] No datapoints for %s in %s", metric_name, namespace)
            return None

        latest = max(datapoints, key=lambda x: x["Timestamp"])
        value = latest.get(stat)
        logging.info("[DEBUG] %s/%s = %s", namespace, metric_name, value)
        return value

    except Exception as e:
        logging.error("[DEBUG] Failed to fetch %s: %s", metric_name, e)
        return None


# ── 2. batch fetch all metrics (for production) ────────────────────────────────

def fetch_all_metrics_batch(instance_id: str, minutes: int = 10) -> dict:
    """
    Fetch all metrics in a single API call using get_metric_data.
    Returns a flat dict: { metric_id: value_or_None }
    """
    _refresh_caches_if_needed()

    now = datetime.now(timezone.utc)
    ec2_dimensions = [{"Name": "InstanceId", "Value": instance_id}]
    volume_ids = _resolve_volume_ids(instance_id)
    cwagent_discovered = _discover_cwagent_metrics(instance_id)
    queries = []

    # ── AWS/EC2 ────────────────────────────────────────────────────────────────
    for metric_name, stat in EC2_METRICS.items():
        queries.append(
            {
                "Id": metric_name.lower(),
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": metric_name,
                        "Dimensions": ec2_dimensions,
                    },
                    "Period": 300,
                    "Stat": stat,
                },
                "ReturnData": True,
            }
        )

    # ── CWAgent ────────────────────────────────────────────────────────────────
    all_cwagent_metrics = {}
    all_cwagent_metrics.update(CWAGENT_METRICS)
    all_cwagent_metrics.update(OPTIONAL_CWAGENT_METRICS)

    for metric_name, stat in all_cwagent_metrics.items():
        dimensions = cwagent_discovered.get(metric_name)
        if not dimensions:
            continue

        queries.append(
            {
                "Id": metric_name.lower(),
                "MetricStat": {
                    "Metric": {
                        "Namespace": "CWAgent",
                        "MetricName": metric_name,
                        "Dimensions": dimensions,
                    },
                    "Period": 300,
                    "Stat": stat,
                },
                "ReturnData": True,
            }
        )

    # ── AWS/EBS ────────────────────────────────────────────────────────────────
    for vol_id in volume_ids:
        safe_vol_id = vol_id.replace("-", "_")

        for metric_name, stat in EBS_METRICS.items():
            queries.append(
                {
                    "Id": f"{metric_name.lower()}_{safe_vol_id}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EBS",
                            "MetricName": metric_name,
                            "Dimensions": [{"Name": "VolumeId", "Value": vol_id}],
                        },
                        "Period": 300,
                        "Stat": stat,
                    },
                    "ReturnData": True,
                }
            )

    if not queries:
        logging.warning("No metric queries built for instance %s", instance_id)
        return {}

    try:
        response = cloudwatch.get_metric_data(
            MetricDataQueries=queries,
            StartTime=now - timedelta(minutes=minutes),
            EndTime=now,
        )
        return _parse_results(response)

    except Exception as e:
        logging.error("Batch metric fetch failed for %s: %s", instance_id, e)
        return {}