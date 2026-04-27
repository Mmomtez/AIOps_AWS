from functools import lru_cache
from pathlib import Path

from ml.models.anomaly_detection.isolation_forest import load_isolation_forest_model


DEFAULT_ISOLATION_FOREST_PATH = Path("ml/models/artifacts/isolation_forest.joblib")


@lru_cache(maxsize=4)
def _load_anomaly_model_cached(model_path: str):
    return load_isolation_forest_model(Path(model_path))


def load_anomaly_model(model_path: str | Path = DEFAULT_ISOLATION_FOREST_PATH):
    path = Path(model_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"Isolation Forest model not found at {path}. "
            "Run backend/pipelines/training_pipeline.py first or place the model artifact there."
        )

    return _load_anomaly_model_cached(str(path))
