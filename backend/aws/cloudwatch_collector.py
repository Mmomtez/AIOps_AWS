# CloudWatch data collector
import boto3
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import os

parent_dir = os.path.dirname(os.path.dirname(__file__))
dotenv_path = os.path.join(parent_dir, "config", ".env")
load_dotenv(dotenv_path)  # Load environment variables from .env file


AWS_REGION = os.getenv("AWS_REGION")


def fetch_cpu_utilization(instance_id):
    cloudwatch = boto3.client("cloudwatch", region_name= AWS_REGION)

    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[
            {"Name": "InstanceId", "Value": instance_id},
        ],
        StartTime=datetime.now(timezone.utc) - timedelta(minutes=10),
        EndTime=datetime.now(timezone.utc),
        Period=300,
        Statistics=["Average"],
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return None

    latest = sorted(datapoints, key=lambda x: x["Timestamp"])[-1]

    return latest["Average"]


def fetch_memory_utilization(instance_id):
    cloudwatch = boto3.client("cloudwatch", region_name= AWS_REGION)
    response = cloudwatch.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="MemoryUtilization",
        Dimensions=[
            {"Name": "InstanceId", "Value": instance_id},
        ],
        StartTime=datetime.now(timezone.utc) - timedelta(minutes=10),
        EndTime=datetime.now(timezone.utc),
        Period=300,
        Statistics=["Average"],
    )

    datapoints = response["Datapoints"]

    if not datapoints:
        return None

    latest = sorted(datapoints, key=lambda x: x["Timestamp"])[-1]

    return latest["Average"]