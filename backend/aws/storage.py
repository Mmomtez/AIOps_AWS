from typing import List
from pathlib import Path
import json
from schemas.metrics import Metrics
from schemas.log_event import LogEvent

def save_metrics(metrics: Metrics):
    with open("metrics.json", "w") as f:
        json.dump(metrics.model_dump(mode="json"), f, indent=2)

def save_logs(logs: List[LogEvent]):
    with open("logs.json", "w") as f:
        json.dump(
            [log.model_dump(mode="json") for log in logs],
            f,
            indent=2
        )