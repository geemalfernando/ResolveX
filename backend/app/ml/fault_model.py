"""Fault inference using an explicitly versioned, locally trusted joblib bundle.

Training must export pipeline, features (in training order), model_name and
model_version. Optional class_mapping maps encoded labels to canonical parties.
No ETA regressor or fabricated classifier is substituted for a missing artifact.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..models import AggregatorInput, CheckName

logger = logging.getLogger(__name__)
PARTIES = {"MERCHANT", "RIDER", "EXTERNAL", "NEITHER"}
from .dataset_config import FAULT_FEATURES
FEATURES = tuple(FAULT_FEATURES)


def extract_features(payload: AggregatorInput) -> dict[str, float]:
    checks = {c.check_name: c.details for c in payload.check_results}
    missing = {CheckName.timing, CheckName.rider_route, CheckName.zone} - set(checks)
    if missing:
        raise ValueError(f"Missing evidence checks: {sorted(c.value for c in missing)}")
    timing, route, zone = checks[CheckName.timing], checks[CheckName.rider_route], checks[CheckName.zone]
    ts = payload.case.order.timestamps
    values = {
        "prep_delay_min": timing.get("prep_delay_minutes") if timing.get("prep_minutes") is not None else None,
        "pickup_delay_min": max(0.0, (ts.picked_up_at - ts.ready_at).total_seconds() / 60) if ts.picked_up_at and ts.ready_at else None,
        "travel_delay_min": timing.get("travel_delay_minutes"),
        "route_deviation_km": max(0, route["total_distance_km"] - route["straight_line_km"]) if "total_distance_km" in route else None,
        "stationary_time_min": route.get("max_stationary_minutes"),
        "zone_late_percentage": zone.get("late_ratio", 0) * 100,
        "zone_average_delay_min": zone.get("average_delay_minutes"),
    }
    return {name: float(values[name]) if values[name] is not None else float("nan") for name in FEATURES}



class FaultModel:
    def __init__(self):
        self.estimator = None
        self.features = []
        self.name = None
        self.version = None
        self.labels = []
        self.label_provenance = None
        self.error = "Fault model has not been initialized"

    def load(self, path: str | Path):
        self.__init__()
        try:
            bundle = joblib.load(path)
            estimator = bundle["pipeline"]
            features = list(bundle["features"])
            if not features or len(set(features)) != len(features) or set(features) - set(FEATURES):
                raise ValueError("Training feature schema contains unsupported or duplicate features")
            if not callable(getattr(estimator, "predict_proba", None)) or not callable(getattr(estimator, "predict", None)):
                raise ValueError("Fault model must implement predict and predict_proba")
            if getattr(estimator, "n_features_in_", None) != len(features):
                raise ValueError("Training feature count differs from estimator")
            if hasattr(estimator, "feature_names_in_") and list(estimator.feature_names_in_) != features:
                raise ValueError("Training feature order differs from estimator")
            mapping = bundle.get("class_mapping", {})
            labels = [str(mapping.get(str(c), c)).upper() for c in estimator.classes_]
            if set(labels) != PARTIES or len(labels) != 4:
                raise ValueError("Model classes must map uniquely to MERCHANT, RIDER, EXTERNAL, NEITHER")
            self.name, self.version = str(bundle["model_name"]), str(bundle["model_version"])
            self.features, self.labels, self.estimator = features, labels, estimator
            self.label_provenance = bundle.get("label_provenance")
            self.error = None
            logger.info("[ML] Fault model loaded: %s version=%s features=%s", self.name, self.version, features)
        except Exception as exc:
            self.error = f"Fault model loading failed: {type(exc).__name__}: {exc}"
            logger.warning("[ML] %s", self.error)

    def status(self):
        model_type = type(self.estimator.steps[-1][1] if hasattr(self.estimator, "steps") else self.estimator).__name__ if self.estimator is not None else None
        nested = {
            "loaded": self.estimator is not None, "type": model_type,
            "model_name": self.name, "model_version": self.version,
            "features": len(self.features), "feature_names": self.features,
            "classes": self.labels, "labels": self.label_provenance,
            "fallback_reason": self.error,
        }
        return {
            "fault_model": nested,
            "fault_model_loaded": nested["loaded"], "fraud_model_loaded": False,
            "fault_model_type": model_type, "model_name": self.name, "model_version": self.version,
            "label_provenance": self.label_provenance,
            "classes": self.labels, "feature_count": len(self.features),
            "feature_names": self.features, "fallback_reason": self.error,
        }

    def infer(self, payload: AggregatorInput) -> dict:
        result = dict(model_used=False, model_name=self.name, model_version=self.version,
                      model_prediction=None, label_provenance=self.label_provenance, class_probabilities={}, features={}, feature_names=self.features,
                      feature_vector=[], fallback_reason=self.error)
        try:
            available = extract_features(payload)
            selected = self.features if self.estimator is not None else list(FEATURES)
            result["features"] = {k: v if np.isfinite(v) else None for k, v in available.items() if k in selected}
            if self.estimator is None:
                return result
            vector = [available[k] for k in self.features]
            result["features"] = {k: result["features"][k] for k in self.features}
            result["feature_vector"] = [v if np.isfinite(v) else None for v in vector]
            frame = pd.DataFrame([vector], columns=self.features)
            prediction = self.estimator.predict(frame)[0]
            probabilities = np.asarray(self.estimator.predict_proba(frame)[0], dtype=float)
            if probabilities.shape != (4,) or not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any() or not np.isclose(probabilities.sum(), 1):
                raise ValueError("Invalid class probability distribution")
            label = self.labels[list(self.estimator.classes_).index(prediction)]
            result.update(model_used=True, model_prediction=label,
                          class_probabilities=dict(zip(self.labels, probabilities.tolist())), fallback_reason=None)
            logger.info("[ML] case=%s features=%s prediction=%s probabilities=%s", payload.case.case_id, result["features"], label, result["class_probabilities"])
        except Exception as exc:
            result["fallback_reason"] = f"Fault inference failed: {type(exc).__name__}: {exc}"
            logger.warning("[ML] case=%s %s", payload.case.case_id, result["fallback_reason"])
        return result


fault_model = FaultModel()
