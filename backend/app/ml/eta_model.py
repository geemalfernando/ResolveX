"""Cached local ETA inference with the same feature contract as training."""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .dataset_config import ETA_FEATURES, MODEL_DIR
from ..models import Case

MODEL_PATH = MODEL_DIR / "eta_model.joblib"
logger = logging.getLogger(__name__)


def build_features(case: Case):
    from ..checks.rider_route import _haversine_m
    placed = case.order.timestamps.placed_at
    late_ratio = case.zone_snapshot.late_orders_count / case.zone_snapshot.open_orders_count if case.zone_snapshot.open_orders_count else 0
    vehicle = case.rider.vehicle.strip().lower() if case.rider else "unknown"
    return {
        "distance_km": _haversine_m(case.merchant.lat, case.merchant.lng, case.customer.lat, case.customer.lng) / 1000,
        "prep_time_min": case.merchant.avg_prep_minutes,
        "order_hour": placed.hour, "is_weekend": int(placed.weekday() >= 5),
        "weather": "unknown",
        "traffic": "jam" if late_ratio >= 0.6 else "high" if late_ratio >= 0.3 else "medium" if late_ratio > 0 else "low",
        "vehicle": {"bike": "motorcycle", "electric_scooter": "electric scooter"}.get(vehicle, vehicle),
    }


class EtaModel:
    def __init__(self):
        self.estimator = None
        self.metadata = {}
        self.error = "ETA model has not been initialized"

    def load(self, path=MODEL_PATH):
        self.__init__()
        try:
            bundle = joblib.load(path)
            if list(bundle["features"]) != ETA_FEATURES or list(bundle["pipeline"].feature_names_in_) != ETA_FEATURES:
                raise ValueError("ETA training feature order does not match runtime")
            self.estimator = bundle["pipeline"]
            self.metadata = {k: bundle.get(k) for k in ["model_name", "model_version", "test_metrics", "test_metrics_by_source", "limitations", "sources"]}
            self.error = None
            logger.info("[ML] ETA model loaded: %s", self.metadata["model_version"])
        except Exception as exc:
            self.error = f"ETA model loading failed: {type(exc).__name__}: {exc}"
            logger.warning("[ML] %s", self.error)

    def status(self):
        loaded = self.estimator is not None
        model_type = type(self.estimator.steps[-1][1]).__name__ if loaded else None
        metrics = self.metadata.get("test_metrics_by_source") or {}
        nested = dict(self.metadata, loaded=loaded, type=model_type, features=ETA_FEATURES,
                      training_sources=[name for name in self.metadata.get("sources", {}) if name != "normalization"],
                      zomato_mae_minutes=metrics.get("zomato", {}).get("mae_min"),
                      kaggle_mae_minutes=metrics.get("kaggle_synthetic", {}).get("mae_min"),
                      fallback_reason=self.error)
        nested.pop("sources", None)
        return {"eta_model_loaded": loaded, "eta_model_type": model_type, "eta_model": nested}

    def predict(self, case):
        if self.estimator is None:
            return None
        try:
            prediction = float(self.estimator.predict(pd.DataFrame([build_features(case)], columns=ETA_FEATURES))[0])
            if not np.isfinite(prediction) or prediction <= 0:
                raise ValueError("ETA prediction must be positive and finite")
            return round(prediction, 1)
        except Exception:
            logger.exception("Local ETA inference failed; using SLA timing baseline")
            return None


eta_model = EtaModel()


def predict_minutes(case: Case) -> float | None:
    return eta_model.predict(case)
