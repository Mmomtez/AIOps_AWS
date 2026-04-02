# Model training pipeline
from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.models.anomaly_detection.isolation_forest import fine_tune_isolation_forest
from ml.models.forecasting.lstm_forecaster import fine_tune_lstm


def fine_tune_models_from_collected_data(
	metrics_dir: str | Path = "data/metrics",
	artifacts_dir: str | Path = "ml/models/artifacts",
	lookback: int = 24,
) -> dict[str, Any]:
	"""Fine-tune Isolation Forest and LSTM using collected CloudWatch metrics."""
	artifacts_path = Path(artifacts_dir)
	artifacts_path.mkdir(parents=True, exist_ok=True)

	if_model_path = artifacts_path / "isolation_forest.joblib"
	lstm_model_path = artifacts_path / "lstm_forecaster.keras"
	lstm_scaler_path = artifacts_path / "lstm_scaler.joblib"

	if_model = fine_tune_isolation_forest(
		metrics_dir=metrics_dir,
		output_path=if_model_path,
	)

	lstm_model, lstm_scaler = fine_tune_lstm(
		metrics_dir=metrics_dir,
		model_path=lstm_model_path,
		scaler_path=lstm_scaler_path,
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
