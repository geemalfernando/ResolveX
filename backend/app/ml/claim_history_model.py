"""Claim-history inference: IsolationForest anomaly + calibrated XGBoost risk.

Applies a stored probability temperature so scores are continuous mid-band
friendly rather than collapsing to ~0 / ~1.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import exp, log
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ..models import RefundHistoryEntry

MODEL_PATH = Path(__file__).with_name("claim_history_model.joblib")
LOOKBACK_DAYS = 90
FEATURES = [
    "claims_last_90_days",
    "claims_last_30_days",
    "approved_ratio",
    "denied_ratio",
    "voucher_ratio",
    "reason_diversity",
    "avg_refund_amount",
    "max_refund_amount",
    "days_since_last_claim",
    "unique_reason_ratio",
]
DEFAULT_TEMPERATURE = 1.6

_bundle: dict[str, Any] | None = None


def extract_features(
    history: list[RefundHistoryEntry],
    now: datetime | None = None,
) -> dict[str, float]:
    now = now or datetime.now(timezone.utc)
    cutoff_90 = now - timedelta(days=LOOKBACK_DAYS)
    cutoff_30 = now - timedelta(days=30)
    recent = [c for c in history if c.created_at >= cutoff_90]
    last_30 = [c for c in recent if c.created_at >= cutoff_30]
    count = len(recent)

    if count == 0:
        return {
            "claims_last_90_days": 0.0,
            "claims_last_30_days": 0.0,
            "approved_ratio": 0.0,
            "denied_ratio": 0.0,
            "voucher_ratio": 0.0,
            "reason_diversity": 0.0,
            "avg_refund_amount": 0.0,
            "max_refund_amount": 0.0,
            "days_since_last_claim": float(LOOKBACK_DAYS),
            "unique_reason_ratio": 0.0,
        }

    approved = sum(1 for c in recent if c.outcome == "approved")
    denied = sum(1 for c in recent if c.outcome == "denied")
    voucher = sum(1 for c in recent if c.outcome == "voucher")
    reasons = {c.reason for c in recent}
    amounts = [c.amount for c in recent]
    newest = max(c.created_at for c in recent)

    return {
        "claims_last_90_days": float(count),
        "claims_last_30_days": float(len(last_30)),
        "approved_ratio": approved / count,
        "denied_ratio": denied / count,
        "voucher_ratio": voucher / count,
        "reason_diversity": float(len(reasons)),
        "avg_refund_amount": sum(amounts) / count,
        "max_refund_amount": max(amounts),
        "days_since_last_claim": max((now - newest).total_seconds() / 86400.0, 0.0),
        "unique_reason_ratio": len(reasons) / count,
    }


def _load_bundle() -> dict[str, Any] | None:
    global _bundle
    if _bundle is not None:
        return _bundle
    if not MODEL_PATH.exists():
        return None
    _bundle = joblib.load(MODEL_PATH)
    return _bundle


def reload_bundle() -> None:
    """Clear cached model so a freshly trained .joblib is picked up."""
    global _bundle
    _bundle = None


def _soften_probability(prob: float, temperature: float) -> float:
    prob = min(max(prob, 1e-6), 1 - 1e-6)
    logit = log(prob / (1 - prob))
    return 1.0 / (1.0 + exp(-logit / max(temperature, 1e-3)))


def predict(history: list[RefundHistoryEntry]) -> dict[str, Any] | None:
    bundle = _load_bundle()
    if bundle is None:
        return None

    features = extract_features(history)
    frame = pd.DataFrame([features], columns=bundle.get("features", FEATURES))
    scaler = bundle["scaler"]
    isolation_forest = bundle["isolation_forest"]
    xgboost = bundle["xgboost"]
    temperature = float(bundle.get("probability_temperature", DEFAULT_TEMPERATURE))

    scaled = scaler.transform(frame)
    anomaly_label = int(isolation_forest.predict(scaled)[0] == -1)
    anomaly_score = float(-isolation_forest.decision_function(scaled)[0])
    raw_probability = float(xgboost.predict_proba(frame)[0][1])
    risk_probability = float(_soften_probability(raw_probability, temperature))

    return {
        "features": {name: round(features[name], 3) for name in FEATURES},
        "anomaly": bool(anomaly_label),
        "anomaly_score": round(anomaly_score, 3),
        "risk_probability_raw": round(raw_probability, 3),
        "risk_probability": round(risk_probability, 3),
        "probability_temperature": temperature,
        "source": "isolation_forest+xgboost",
    }
