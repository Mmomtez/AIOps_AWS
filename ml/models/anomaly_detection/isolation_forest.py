from __future__ import annotations

import json
import os
from importlib import import_module
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


def load_metrics_dataframe(
	bucket_name: str | None = None,
	prefix: str = "metrics/",
	metric_columns: Iterable[str] | None = None,
) -> pd.DataFrame:
	"""Load collected metrics JSON objects from S3 into a clean DataFrame."""
	bucket = bucket_name or os.getenv("S3_BUCKET_NAME")
	if not bucket:
		raise ValueError("S3 bucket name is required. Pass bucket_name or set S3_BUCKET_NAME.")

	columns = list(metric_columns or DEFAULT_METRIC_COLUMNS)
	rows: list[dict[str, Any]] = []
	boto3 = import_module("boto3")
	s3_client = boto3.client("s3")
	paginator = s3_client.get_paginator("list_objects_v2")
	normalized_prefix = prefix.rstrip("/") + "/" if prefix else ""

	for page in paginator.paginate(Bucket=bucket, Prefix=normalized_prefix):
		for item in page.get("Contents", []):
			key = item.get("Key", "")
			if not key.endswith(".json"):
				continue

			obj = s3_client.get_object(Bucket=bucket, Key=key)
			payload = json.loads(obj["Body"].read().decode("utf-8"))

			if isinstance(payload, list):
				continue

			row = {col: float(payload.get(col, 0.0) or 0.0) for col in columns}
			row["instance_id"] = payload.get("instance_id", "")
			row["timestamp"] = payload.get("timestamp")
			rows.append(row)

	if not rows:
		raise ValueError(f"No metrics JSON files found in s3://{bucket}/{normalized_prefix}")

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
	output_path: str | Path,
	bucket_name: str | None = None,
	prefix: str = "metrics/",
	feature_columns: Iterable[str] | None = None,
	contamination: float = 0.05,
	random_state: int = 42,
) -> Pipeline:
	"""
	Re-fit the Isolation Forest with the latest collected metrics.

	Isolation Forest does not support incremental updates, so "fine-tuning"
	here means retraining on the current metrics history.
	"""
	df = load_metrics_dataframe(
		bucket_name=bucket_name,
		prefix=prefix,
		metric_columns=feature_columns,
	)
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
