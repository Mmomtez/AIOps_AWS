from __future__ import annotations

import json
import os
from importlib import import_module
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

try:
	from tensorflow.keras.callbacks import EarlyStopping
	from tensorflow.keras.layers import LSTM, Dense
	from tensorflow.keras.models import Sequential, load_model
	from tensorflow.keras.optimizers import Adam
except Exception as exc:  # pragma: no cover
	raise ImportError(
		"TensorFlow is required for LSTM training/prediction. "
		"Install it with pip install tensorflow"
	) from exc


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
	bucket = bucket_name or os.getenv("S3_BUCKET_NAME")
	if not bucket:
		raise ValueError("S3 bucket name is required. Pass bucket_name or set S3_BUCKET_NAME.")

	columns = list(metric_columns or DEFAULT_METRIC_COLUMNS)
	rows: list[dict[str, float | str | None]] = []
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

			row = {c: float(payload.get(c, 0.0) or 0.0) for c in columns}
			row["timestamp"] = payload.get("timestamp")
			rows.append(row)

	if not rows:
		raise ValueError(f"No metrics JSON files found in s3://{bucket}/{normalized_prefix}")

	df = pd.DataFrame(rows)
	df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
	df = df.sort_values("timestamp").reset_index(drop=True)
	return df


def _make_sequences(values: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
	X, y = [], []
	for idx in range(lookback, len(values)):
		X.append(values[idx - lookback : idx])
		y.append(values[idx])
	return np.asarray(X), np.asarray(y)


def _build_lstm(input_steps: int, n_features: int, learning_rate: float = 1e-3) -> Sequential:
	model = Sequential(
		[
			LSTM(64, input_shape=(input_steps, n_features), return_sequences=True),
			LSTM(32),
			Dense(n_features),
		]
	)
	model.compile(optimizer=Adam(learning_rate=learning_rate), loss="mae")
	return model


def train_lstm_forecaster(
	data: pd.DataFrame,
	feature_columns: Iterable[str] | None = None,
	lookback: int = 24,
	epochs: int = 20,
	batch_size: int = 32,
	validation_split: float = 0.2,
) -> tuple[Sequential, MinMaxScaler]:
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	raw = data[columns].fillna(0.0).values

	scaler = MinMaxScaler()
	scaled = scaler.fit_transform(raw)

	if len(scaled) <= lookback:
		raise ValueError(f"Need more than lookback={lookback} rows to train LSTM")

	X, y = _make_sequences(scaled, lookback=lookback)
	model = _build_lstm(input_steps=lookback, n_features=len(columns))

	early_stop = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)
	model.fit(
		X,
		y,
		epochs=epochs,
		batch_size=batch_size,
		validation_split=validation_split,
		callbacks=[early_stop],
		verbose=0,
	)
	return model, scaler


def fine_tune_lstm(
	model_path: str | Path,
	scaler_path: str | Path,
	bucket_name: str | None = None,
	prefix: str = "metrics/",
	feature_columns: Iterable[str] | None = None,
	lookback: int = 24,
	epochs: int = 8,
	batch_size: int = 32,
) -> tuple[Sequential, MinMaxScaler]:
	"""Fine-tune an LSTM using latest collected metrics history."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	df = load_metrics_dataframe(
		bucket_name=bucket_name,
		prefix=prefix,
		metric_columns=columns,
	)

	raw = df[columns].fillna(0.0).values
	if len(raw) <= lookback:
		raise ValueError(f"Need more than lookback={lookback} rows to fine-tune LSTM")

	model_file = Path(model_path)
	scaler_file = Path(scaler_path)

	if model_file.exists() and scaler_file.exists():
		model = load_model(model_file)
		scaler: MinMaxScaler = joblib.load(scaler_file)
		scaled = scaler.transform(raw)
	else:
		model = _build_lstm(input_steps=lookback, n_features=len(columns))
		scaler = MinMaxScaler()
		scaled = scaler.fit_transform(raw)

	X, y = _make_sequences(scaled, lookback=lookback)
	model.fit(X, y, epochs=epochs, batch_size=batch_size, verbose=0)

	save_lstm_artifacts(model=model, scaler=scaler, model_path=model_file, scaler_path=scaler_file)
	return model, scaler


def predict_next_values(
	model: Sequential,
	scaler: MinMaxScaler,
	recent_data: pd.DataFrame,
	feature_columns: Iterable[str] | None = None,
	lookback: int = 24,
) -> dict[str, float]:
	"""Predict next-step metric values from recent history."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	if len(recent_data) < lookback:
		raise ValueError(f"Need at least {lookback} rows in recent_data")

	window = recent_data[columns].fillna(0.0).tail(lookback).values
	window_scaled = scaler.transform(window)
	X = np.expand_dims(window_scaled, axis=0)

	pred_scaled = model.predict(X, verbose=0)[0]
	pred = scaler.inverse_transform(np.expand_dims(pred_scaled, axis=0))[0]

	return {col: float(value) for col, value in zip(columns, pred)}


def forecast_horizon(
	model: Sequential,
	scaler: MinMaxScaler,
	recent_data: pd.DataFrame,
	steps: int,
	feature_columns: Iterable[str] | None = None,
	lookback: int = 24,
) -> pd.DataFrame:
	"""Forecast multiple future steps recursively."""
	columns = list(feature_columns or DEFAULT_METRIC_COLUMNS)
	if steps < 1:
		raise ValueError("steps must be >= 1")

	history = recent_data[columns].fillna(0.0).copy()
	forecasts: list[dict[str, float]] = []

	for _ in range(steps):
		next_point = predict_next_values(
			model=model,
			scaler=scaler,
			recent_data=history,
			feature_columns=columns,
			lookback=lookback,
		)
		forecasts.append(next_point)
		history = pd.concat([history, pd.DataFrame([next_point])], ignore_index=True)

	return pd.DataFrame(forecasts)


def save_lstm_artifacts(
	model: Sequential,
	scaler: MinMaxScaler,
	model_path: str | Path,
	scaler_path: str | Path,
) -> None:
	model_file = Path(model_path)
	scaler_file = Path(scaler_path)
	model_file.parent.mkdir(parents=True, exist_ok=True)
	scaler_file.parent.mkdir(parents=True, exist_ok=True)

	model.save(model_file)
	joblib.dump(scaler, scaler_file)


def load_lstm_artifacts(
	model_path: str | Path,
	scaler_path: str | Path,
) -> tuple[Sequential, MinMaxScaler]:
	model = load_model(model_path)
	scaler: MinMaxScaler = joblib.load(scaler_path)
	return model, scaler
