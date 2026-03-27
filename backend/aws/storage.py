from typing import List
from pathlib import Path
import json

from schemas.metrics import Metrics
from schemas.log_event import LogEvent


def save_metrics(metrics: Metrics):
    # create folder if not exists
    path = Path("./data/metrics")
    path.mkdir(parents=True, exist_ok=True)

    # create unique filename using timestamp + instance_id
    timestamp = metrics.timestamp.isoformat().replace(":", "-")
    filename = f"{metrics.instance_id}_{timestamp}.json"

    file_path = path / filename

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(metrics.model_dump(mode="json"), f, indent=2)

    print(f"Metrics saved to {file_path}")

def save_logs(logs: List[LogEvent]):
    if not logs:
        return

    path = Path("./data/logs")
    path.mkdir(parents=True, exist_ok=True)

    timestamp = logs[0].timestamp.isoformat().replace(":", "-")
    filename = f"{logs[0].instance_id}_{timestamp}.json"

    file_path = path / filename

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(
            [log.model_dump(mode="json") for log in logs],
            f,
            indent=2
        )

    print(f"Logs saved to {file_path}")