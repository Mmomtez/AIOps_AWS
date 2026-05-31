from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("INSTANCE_ID", "i-local")
os.environ.setdefault("S3_BUCKET_NAME", "local-bucket")
os.environ.setdefault("LOG_GROUP_NAME", "local-log-group")

from backend.api.auth import router as auth_router
from backend.api.instances import router as instances_router
from backend.db.base import Base
from backend.db.session import get_db


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(instances_router)

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


def _sample_instances() -> list[dict]:
    launch_time = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    return [
        {
            "InstanceId": "i-running123",
            "InstanceType": "t3.micro",
            "State": {"Name": "running"},
            "Placement": {"AvailabilityZone": "us-east-1a"},
            "PrivateIpAddress": "10.0.0.10",
            "PublicIpAddress": "54.1.2.3",
            "LaunchTime": launch_time,
            "Tags": [{"Key": "Name", "Value": "web-1"}],
        },
        {
            "InstanceId": "i-stopped456",
            "InstanceType": "t3.small",
            "State": {"Name": "stopped"},
            "Placement": {"AvailabilityZone": "us-east-1b"},
            "LaunchTime": launch_time,
            "Tags": [],
        },
    ]


def _mock_paginator(instances: list[dict]) -> MagicMock:
    paginator = MagicMock()
    paginator.paginate.return_value = [{"Reservations": [{"Instances": instances}]}]
    return paginator


def _login(client: TestClient) -> str:
    client.post("/auth/register", json={"email": "aws@example.com", "password": "StrongPass123"})
    response = client.post("/auth/login", json={"email": "aws@example.com", "password": "StrongPass123"})
    return response.json()["tokens"]["access_token"]


@patch("backend.aws.ec2_service._ec2_client")
def test_list_instances(mock_ec2_client: MagicMock, client: TestClient) -> None:
    mock_client = MagicMock()
    mock_ec2_client.return_value = mock_client
    mock_client.get_paginator.return_value = _mock_paginator(_sample_instances())

    token = _login(client)
    response = client.get("/api/instances", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["region"] == "us-east-1"
    assert body["total"] == 2
    assert body["items"][0]["instance_id"] == "i-running123"
    assert body["items"][0]["name"] == "web-1"
    assert body["items"][1]["state"] == "stopped"


@patch("backend.aws.ec2_service._ec2_client")
def test_list_instances_requires_auth(mock_ec2_client: MagicMock, client: TestClient) -> None:
    response = client.get("/api/instances")
    assert response.status_code == 401


@patch("backend.aws.ec2_service._ec2_client")
def test_list_instances_invalid_state(mock_ec2_client: MagicMock, client: TestClient) -> None:
    token = _login(client)
    response = client.get("/api/instances?state=broken", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 400


@patch("backend.aws.ec2_service._ec2_client")
def test_instance_summary(mock_ec2_client: MagicMock, client: TestClient) -> None:
    mock_client = MagicMock()
    mock_ec2_client.return_value = mock_client
    mock_client.get_paginator.return_value = _mock_paginator(_sample_instances())

    token = _login(client)
    response = client.get("/api/instances/summary", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {"state": "running", "count": 1} in body["by_state"]
    assert {"state": "stopped", "count": 1} in body["by_state"]


@patch("backend.aws.ec2_service._ec2_client")
def test_get_instance_by_id(mock_ec2_client: MagicMock, client: TestClient) -> None:
    mock_client = MagicMock()
    mock_ec2_client.return_value = mock_client
    mock_client.describe_instances.return_value = {
        "Reservations": [{"Instances": [_sample_instances()[0]]}]
    }

    token = _login(client)
    response = client.get("/api/instances/i-running123", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["instance_id"] == "i-running123"
    assert response.json()["name"] == "web-1"
