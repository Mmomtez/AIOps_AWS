from __future__ import annotations

from pydantic import BaseModel, Field


class Ec2InstanceSummary(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier (e.g. i-0123456789abcdef0)")
    name: str | None = Field(default=None, description="Value of the Name tag, if set")
    state: str = Field(..., description="Instance state (running, stopped, etc.)")
    instance_type: str = Field(..., description="EC2 instance type")
    availability_zone: str | None = Field(default=None, description="Availability zone")
    private_ip: str | None = Field(default=None, description="Private IPv4 address")
    public_ip: str | None = Field(default=None, description="Public IPv4 address")
    launch_time: str | None = Field(default=None, description="ISO 8601 launch timestamp")


class Ec2InstanceListResponse(BaseModel):
    region: str
    total: int
    items: list[Ec2InstanceSummary]


class Ec2StateCount(BaseModel):
    state: str
    count: int


class Ec2InstanceSummaryResponse(BaseModel):
    region: str
    total: int
    by_state: list[Ec2StateCount]
