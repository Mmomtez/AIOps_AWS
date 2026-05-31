from __future__ import annotations

from collections import Counter
from datetime import datetime

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from backend.config.settings import AWS_REGION
from backend.schemas.ec2 import Ec2InstanceListResponse, Ec2InstanceSummary, Ec2InstanceSummaryResponse, Ec2StateCount

_VALID_STATES = {
    "pending",
    "running",
    "shutting-down",
    "terminated",
    "stopping",
    "stopped",
}


def _ec2_client(region: str | None = None):
    return boto3.client("ec2", region_name=region or AWS_REGION)


def _tag_value(tags: list[dict] | None, key: str) -> str | None:
    for tag in tags or []:
        if tag.get("Key") == key:
            return tag.get("Value")
    return None


def _format_launch_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _to_summary(instance: dict) -> Ec2InstanceSummary:
    return Ec2InstanceSummary(
        instance_id=instance["InstanceId"],
        name=_tag_value(instance.get("Tags"), "Name"),
        state=instance["State"]["Name"],
        instance_type=instance["InstanceType"],
        availability_zone=instance.get("Placement", {}).get("AvailabilityZone"),
        private_ip=instance.get("PrivateIpAddress"),
        public_ip=instance.get("PublicIpAddress"),
        launch_time=_format_launch_time(instance.get("LaunchTime")),
    )


def _normalize_states(states: list[str] | None) -> list[str] | None:
    if not states:
        return None

    normalized: list[str] = []
    for state in states:
        cleaned = state.strip().lower()
        if not cleaned:
            continue
        if cleaned not in _VALID_STATES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid state '{state}'. Allowed: {', '.join(sorted(_VALID_STATES))}",
            )
        if cleaned not in normalized:
            normalized.append(cleaned)
    return normalized or None


def _fetch_instances(region: str | None, states: list[str] | None) -> list[dict]:
    client = _ec2_client(region)
    filters = []
    if states:
        filters.append({"Name": "instance-state-name", "Values": states})

    try:
        paginator = client.get_paginator("describe_instances")
        pages = paginator.paginate(**({"Filters": filters} if filters else {}))
        instances: list[dict] = []
        for page in pages:
            for reservation in page.get("Reservations", []):
                instances.extend(reservation.get("Instances", []))
        return instances
    except (ClientError, BotoCoreError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch EC2 instances from AWS: {exc}",
        ) from exc


def list_instances(region: str | None = None, states: list[str] | None = None) -> Ec2InstanceListResponse:
    resolved_region = region or AWS_REGION
    normalized_states = _normalize_states(states)
    raw_instances = _fetch_instances(resolved_region, normalized_states)
    items = sorted((_to_summary(instance) for instance in raw_instances), key=lambda item: item.instance_id)
    return Ec2InstanceListResponse(region=resolved_region, total=len(items), items=items)


def get_instance(instance_id: str, region: str | None = None) -> Ec2InstanceSummary:
    resolved_region = region or AWS_REGION
    client = _ec2_client(resolved_region)
    try:
        response = client.describe_instances(InstanceIds=[instance_id])
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "")
        if error_code in {"InvalidInstanceID.NotFound", "InvalidInstanceID.Malformed"}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found") from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch EC2 instance from AWS: {exc}",
        ) from exc
    except BotoCoreError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch EC2 instance from AWS: {exc}",
        ) from exc

    instances = [
        instance
        for reservation in response.get("Reservations", [])
        for instance in reservation.get("Instances", [])
    ]
    if not instances:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return _to_summary(instances[0])


def summarize_instances(region: str | None = None) -> Ec2InstanceSummaryResponse:
    resolved_region = region or AWS_REGION
    raw_instances = _fetch_instances(resolved_region, states=None)
    counts = Counter(instance["State"]["Name"] for instance in raw_instances)
    by_state = [Ec2StateCount(state=state, count=count) for state, count in sorted(counts.items())]
    return Ec2InstanceSummaryResponse(region=resolved_region, total=len(raw_instances), by_state=by_state)
