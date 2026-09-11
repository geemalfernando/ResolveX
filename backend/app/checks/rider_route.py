"""RIDER_ROUTE check — plain code geometry.

Uses the rider's GPS trail to flag:
  - a detour (actual path much longer than the straight-line pickup->dropoff distance)
  - a long stationary stop (rider not moving for an unusually long time mid-route)
  - a drop-off pin far from the customer's delivery address
"""

from __future__ import annotations

import math

from ..config import get_settings
from ..models import Case, CheckName, CheckResult, GpsPoint

EARTH_RADIUS_M = 6371000.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _find_stationary_stretches(trail: list[GpsPoint], radius_m: float = 40.0) -> list[dict]:
    """Group consecutive points that stay within `radius_m` of each other and report their duration."""
    stretches: list[dict] = []
    if len(trail) < 2:
        return stretches

    start_idx = 0
    for i in range(1, len(trail)):
        dist = _haversine_m(trail[start_idx].lat, trail[start_idx].lng, trail[i].lat, trail[i].lng)
        if dist > radius_m:
            duration_min = (trail[i - 1].recorded_at - trail[start_idx].recorded_at).total_seconds() / 60.0
            if duration_min > 0:
                stretches.append(
                    {"lat": trail[start_idx].lat, "lng": trail[start_idx].lng, "minutes": round(duration_min, 1)}
                )
            start_idx = i

    duration_min = (trail[-1].recorded_at - trail[start_idx].recorded_at).total_seconds() / 60.0
    if duration_min > 0:
        stretches.append(
            {"lat": trail[start_idx].lat, "lng": trail[start_idx].lng, "minutes": round(duration_min, 1)}
        )
    return stretches


def run(case: Case) -> CheckResult:
    settings = get_settings()
    trail = case.rider_gps_trail

    if len(trail) < 2:
        return CheckResult(
            check_name=CheckName.rider_route,
            flagged=False,
            confidence=0.3,
            summary="Not enough GPS points to evaluate the rider route.",
            details={"issues": [], "reason": "insufficient_gps_data"},
        )

    total_distance_m = sum(
        _haversine_m(trail[i].lat, trail[i].lng, trail[i + 1].lat, trail[i + 1].lng)
        for i in range(len(trail) - 1)
    )
    straight_line_m = _haversine_m(trail[0].lat, trail[0].lng, trail[-1].lat, trail[-1].lng)
    detour_ratio = (total_distance_m / straight_line_m) if straight_line_m > 0 else 1.0

    stationary_stretches = _find_stationary_stretches(trail)
    max_stationary_minutes = max((s["minutes"] for s in stationary_stretches), default=0.0)

    dropoff_point = trail[-1]
    dropoff_distance_m = _haversine_m(
        dropoff_point.lat, dropoff_point.lng, case.customer.lat, case.customer.lng
    )

    issues: list[str] = []
    if detour_ratio >= settings.rider_detour_ratio_threshold:
        issues.append("long_detour")
    if max_stationary_minutes >= settings.rider_stationary_minutes_threshold:
        issues.append("long_stationary_stop")
    if dropoff_distance_m >= settings.rider_dropoff_distance_threshold_m:
        issues.append("dropoff_far_from_address")

    flagged = len(issues) > 0
    confidence = 0.55 + 0.15 * len(issues) if flagged else 0.85

    if flagged:
        summary = f"Rider route issues detected: {', '.join(issues)}."
    else:
        summary = "Rider route looks normal — no detours or unusual stops."

    stationary_points = [s for s in stationary_stretches if s["minutes"] >= settings.rider_stationary_minutes_threshold]

    return CheckResult(
        check_name=CheckName.rider_route,
        flagged=flagged,
        confidence=round(min(confidence, 0.99), 2),
        summary=summary,
        details={
            "total_distance_km": round(total_distance_m / 1000, 2),
            "straight_line_km": round(straight_line_m / 1000, 2),
            "detour_ratio": round(detour_ratio, 2),
            "max_stationary_minutes": max_stationary_minutes,
            "stationary_points": stationary_points,
            "dropoff_distance_from_address_m": round(dropoff_distance_m, 0),
            "issues": issues,
        },
    )
