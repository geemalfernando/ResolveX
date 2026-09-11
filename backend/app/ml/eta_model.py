from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from ..models import Case

MODEL_PATH = Path(__file__).with_name("eta_model.joblib")


def _distance_km(case: Case) -> float:
    from ..checks.rider_route import _haversine_m

    return _haversine_m(
        case.merchant.lat,
        case.merchant.lng,
        case.customer.lat,
        case.customer.lng,
    ) / 1000.0


def build_features(case: Case) -> dict[str, Any]:
    placed_at = case.order.timestamps.placed_at
    pickup_at = case.order.timestamps.picked_up_at
    order_hour = placed_at.hour
    pickup_hour = pickup_at.hour if pickup_at else order_hour
    return {
        "distance_km": _distance_km(case),
        "prep_time_min": case.merchant.avg_prep_minutes,
        "order_hour": order_hour,
        "pickup_hour": pickup_hour,
        "order_day_of_week": placed_at.weekday(),
        "is_weekend": int(placed_at.weekday() >= 5),
        "is_peak_hour": int(order_hour in (12, 13, 14, 19, 20, 21, 22)),
        "multiple_deliveries": 0,
        "weather": "Sunny",
        "traffic": "High" if case.zone_snapshot.late_orders_count else "Medium",
        "vehicle": case.rider.vehicle if case.rider else "motorcycle",
    }


def predict_minutes(case: Case) -> float | None:
    if not MODEL_PATH.exists():
        return None
    bundle = joblib.load(MODEL_PATH)
    prediction = bundle["pipeline"].predict([build_features(case)])[0]
    return round(float(prediction), 1)