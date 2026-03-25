import json
from schemas.metrics import Metrics


def save_metrics(metrics: Metrics):
    with open("metrics.json", "w") as f:
        json.dump(metrics.model_dump(mode="json"), f, indent=2)