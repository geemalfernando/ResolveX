"""Rider-route inference: IsolationForest over GPS geometry features."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).with_name("route_model.joblib")
FEATURES = [
    "detour_ratio",
    "max_stationary_minutes",
    "dropoff_distance_m",
    "total_distance_km",
    "straight_line_km",
    "avg_speed_kmh",
    "stop_count",
    "n_points",
]

_bundle: dict[str, Any] | None = None


def _load_bundle() -> dict[str, Any] | None:
    global _bundle
    if _bundle is not None:
        return _bundle
    if not MODEL_PATH.exists():
        return None
    _bundle = joblib.load(MODEL_PATH)
    return _bundle


def predict(features: dict[str, float]) -> dict[str, Any] | None:
    bundle = _load_bundle()
    if bundle is None:
        return None

    row = {name: float(features.get(name, 0.0)) for name in bundle.get("features", FEATURES)}
    frame = pd.DataFrame([row], columns=bundle.get("features", FEATURES))
    scaler = bundle["scaler"]
    isolation_forest = bundle["isolation_forest"]
    scaled = scaler.transform(frame)
    anomaly = bool(isolation_forest.predict(scaled)[0] == -1)
    anomaly_score = float(-isolation_forest.decision_function(scaled)[0])

    return {
        "anomaly": anomaly,
        "anomaly_score": round(anomaly_score, 3),
        "source": "isolation_forest",
    }
