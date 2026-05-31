from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_current_user
from backend.aws.ec2_service import get_instance, list_instances, summarize_instances
from backend.models.auth import User
from backend.schemas.ec2 import Ec2InstanceListResponse, Ec2InstanceSummary, Ec2InstanceSummaryResponse

router = APIRouter(prefix="/api/instances", tags=["instances"])


@router.get("", response_model=Ec2InstanceListResponse)
def get_instances(
    state: list[str] | None = Query(default=None, description="Filter by instance state (repeatable)"),
    _: User = Depends(get_current_user),
):
    return list_instances(states=state)


@router.get("/summary", response_model=Ec2InstanceSummaryResponse)
def get_instance_summary(_: User = Depends(get_current_user)):
    return summarize_instances()


@router.get("/{instance_id}", response_model=Ec2InstanceSummary)
def get_instance_by_id(instance_id: str, _: User = Depends(get_current_user)):
    return get_instance(instance_id)
