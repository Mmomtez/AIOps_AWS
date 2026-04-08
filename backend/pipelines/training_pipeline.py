# Model training pipeline
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Allow running this file directly: python backend/pipelines/training_pipeline.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(0, str(PROJECT_ROOT))

from ml.models.anomaly_detection.isolation_forest import fine_tune_isolation_forest
from ml.models.forecasting.lstm_forecaster import fine_tune_lstm


def _read_s3_bucket_from_example_env() -> str | None:
	env_example = PROJECT_ROOT / "backend" / "config" / ".env"
	if not env_example.exists():
		return None

	for line in env_example.read_text(encoding="utf-8").splitlines():
		entry = line.strip()
		if not entry or entry.startswith("#") or "=" not in entry:
			continue
		key, value = entry.split("=", 1)
		if key.strip() == "S3_BUCKET_NAME":
			return value.strip()

	return None


def fine_tune_models_from_collected_data(
	metrics_dir: str | Path = "data/metrics",
	s3_bucket_name: str | None = None,
	s3_metrics_prefix: str = "metrics/",
	artifacts_dir: str | Path = "ml/models/artifacts",
	lookback: int = 24,
) -> dict[str, Any]:
	"""Fine-tune Isolation Forest and LSTM using collected CloudWatch metrics."""
	resolved_bucket = s3_bucket_name or _read_s3_bucket_from_example_env()

	artifacts_path = Path(artifacts_dir)
	artifacts_path.mkdir(parents=True, exist_ok=True)

	if_model_path = artifacts_path / "isolation_forest.joblib"
	lstm_model_path = artifacts_path / "lstm_forecaster.keras"
	lstm_scaler_path = artifacts_path / "lstm_scaler.joblib"

	if_model = fine_tune_isolation_forest(
		bucket_name=resolved_bucket,
		prefix=s3_metrics_prefix,
		output_path=if_model_path,
	)

	lstm_model, lstm_scaler = fine_tune_lstm(
		model_path=lstm_model_path,
		scaler_path=lstm_scaler_path,
		bucket_name=resolved_bucket,
		prefix=s3_metrics_prefix,
		lookback=lookback,
	)

	return {
		"if_model": if_model,
		"if_model_path": str(if_model_path),
		"lstm_model": lstm_model,
		"lstm_scaler": lstm_scaler,
		"lstm_model_path": str(lstm_model_path),
		"lstm_scaler_path": str(lstm_scaler_path),
	}


if __name__ == "__main__":
	artifacts = fine_tune_models_from_collected_data()
	print("Fine-tuning completed")
	print(f"Isolation Forest saved at: {artifacts['if_model_path']}")
	print(f"LSTM model saved at: {artifacts['lstm_model_path']}")
	print(f"LSTM scaler saved at: {artifacts['lstm_scaler_path']}")
