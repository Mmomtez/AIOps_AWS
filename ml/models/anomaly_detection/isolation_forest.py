from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


DEFAULT_METRIC_COLUMNS = [
	"cpu",
	"memory",
	"gpu_utilization",
	"gpu_memory_utilization",
	"gpu_encoder_session_count",
	"network_in",
	"network_out",
	"network_packets_in",
	"network_packets_out",
	"disk_read_ops",
	"disk_write_ops",
	"disk_read_bytes",
	"disk_write_bytes",
	"volume_read_bytes",
	"volume_write_bytes",
	"volume_read_ops",
	"volume_write_ops",
]


def _resolve_metrics_dir(metrics_dir: str | Path) -> Path:
	path = Path(metrics_dir)
	if path.exists():
		return path

	fallbacks = [Path("data/metrics"), Path("backend/data/metrics")]
	for candidate in fallbacks:
		if candidate.exists():
			return candidate

	raise FileNotFoundError(f"Metrics directory not found: {path}")


def load_metrics_dataframe(
	metrics_dir: str | Path,
	metric_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
	"""Load collected metrics JSON files into a clean DataFrame."""
	metrics_path = _resolve_metrics_dir(metrics_dir)

	columns = list(metric_columns or DEFAULT_METRIC_COLUMNS)
	rows: list[dict[str, Any]] = []

	for json_file in sorted(metrics_path.glob("*.json")):
		with json_file.open("r", encoding="utf-8") as f:
			payload = json.load(f)

		if isinstance(payload, list):
			continue

		row = {col: float(payload.get(col, 0.0) or 0.0) for col in columns}
		row["instance_id"] = payload.get("instance_id", "")
		row["timestamp"] = payload.get("timestamp")
		rows.append(row)

	if not rows:
		raise ValueError(f"No metrics JSON files found in: {metrics_path}")

	df = pd.DataFrame(rows)
	df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
	df = df.sort_values("timestamp").reset_index(drop=True)
	return df


def train_isolation_forest(
	data: pd.DataFrame,
	feature_columns: Iterable[str] | None = None,
	contamination: float = 0.05,
	random_state: int = 42,
) -> Pipeline:
	"""Train a standardized Isolation Forest pipeline."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	X = data[columns].fillna(0.0)

	model = Pipeline(
		steps=[
			("scaler", StandardScaler()),
			(
				"iforest",
				IsolationForest(
					contamination=contamination,
					random_state=random_state,
					n_estimators=300,
				),
			),
		]
	)
	model.fit(X)
	return model


def fine_tune_isolation_forest(
	metrics_dir: str | Path,
	output_path: str | Path,
	feature_columns: Iterable[str] | None = None,
	contamination: float = 0.05,
	random_state: int = 42,
) -> Pipeline:
	"""
	Re-fit the Isolation Forest with the latest collected metrics.

	Isolation Forest does not support incremental updates, so "fine-tuning"
	here means retraining on the current metrics history.
	"""
	df = load_metrics_dataframe(metrics_dir=metrics_dir, metric_columns=feature_columns)
	model = train_isolation_forest(
		data=df,
		feature_columns=feature_columns,
		contamination=contamination,
		random_state=random_state,
	)
	save_isolation_forest_model(model, output_path)
	return model


def predict_anomalies(
	model: Pipeline,
	data: pd.DataFrame,
	feature_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
	"""Run anomaly prediction and return labels/scores."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	X = data[columns].fillna(0.0)

	labels = model.predict(X)
	scores = model.decision_function(X)

	result = data.copy()
	result["if_label"] = labels
	result["is_anomaly"] = result["if_label"] == -1
	result["if_score"] = scores
	return result


def predict_single_metrics_point(
	model: Pipeline,
	metrics_row: dict[str, float],
	feature_columns: Iterable[str] | None = None,
) -> dict[str, float | bool | int]:
	"""Predict anomaly status for one metrics record."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	row_df = pd.DataFrame([{c: float(metrics_row.get(c, 0.0) or 0.0) for c in columns}])

	label = int(model.predict(row_df)[0])
	score = float(model.decision_function(row_df)[0])

	return {
		"if_label": label,
		"is_anomaly": label == -1,
		"if_score": score,
	}


def save_isolation_forest_model(model: Pipeline, output_path: str | Path) -> None:
	path = Path(output_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	joblib.dump(model, path)


def load_isolation_forest_model(model_path: str | Path) -> Pipeline:
	return joblib.load(model_path)
