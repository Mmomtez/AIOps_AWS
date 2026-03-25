from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Metrics(BaseModel):
    instance_id: str = Field(..., description="EC2 instance identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when metrics were collected",
    )

    # Core
    cpu: float = Field(default=0.0, description="CPU utilization percentage (AWS/EC2)")
    memory: float = Field(default=0.0, description="Memory utilization percentage (CWAgent)")

    # GPU
    gpu_utilization: float = Field(default=0.0, description="GPU utilization percentage")
    gpu_memory_utilization: float = Field(default=0.0, description="GPU memory utilization percentage")
    gpu_encoder_session_count: float = Field(default=0.0, description="Active GPU encoding sessions")

    # Network
    network_in: float = Field(default=0.0, description="Bytes received on all network interfaces")
    network_out: float = Field(default=0.0, description="Bytes sent on all network interfaces")
    network_packets_in: float = Field(default=0.0, description="Packets received by the instance")
    network_packets_out: float = Field(default=0.0, description="Packets sent by the instance")

    # Instance store disk
    disk_read_ops: float = Field(default=0.0, description="Read operations on instance store")
    disk_write_ops: float = Field(default=0.0, description="Write operations on instance store")
    disk_read_bytes: float = Field(default=0.0, description="Bytes read from instance store")
    disk_write_bytes: float = Field(default=0.0, description="Bytes written to instance store")

    # EBS volumes
    volume_read_bytes: float = Field(default=0.0, description="Bytes read from EBS volumes")
    volume_write_bytes: float = Field(default=0.0, description="Bytes written to EBS volumes")
    volume_read_ops: float = Field(default=0.0, description="Read operations on EBS volumes")
    volume_write_ops: float = Field(default=0.0, description="Write operations on EBS volumes")