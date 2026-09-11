"""Shared helpers for seed_data.py and replay_feed.py — Supabase client, zone geography,
and GPS route interpolation. Kept dependency-light and standalone (no backend/ imports)
so the two scripts can run without installing the FastAPI app.
"""

from __future__ import annotations

import math
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Demo city center (Colombo) — swap for wherever you're presenting.
CITY_CENTER = (6.9271, 79.8612)

# Four delivery zones, each a rough lat/lng offset from the city center (~2-3km apart).
ZONES = {
    "ZONE_A": (0.000, 0.000),
    "ZONE_B": (0.025, 0.015),
    "ZONE_C": (-0.020, 0.020),
    "ZONE_D": (0.010, -0.025),
}

LIVE_ORDERS_PLAN_PATH = Path(__file__).resolve().parent / "seed_output" / "live_orders_plan.json"


def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY are not set. Copy .env.example to .env and fill them in "
            "(use the service role key here, not the anon key, so seeding bypasses RLS)."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def zone_point(zone_id: str, spread: float = 0.01) -> tuple[float, float]:
    """A jittered lat/lng inside the given zone."""
    base_lat, base_lng = CITY_CENTER
    offset_lat, offset_lng = ZONES[zone_id]
    return (
        base_lat + offset_lat + random.uniform(-spread, spread),
        base_lng + offset_lng + random.uniform(-spread, spread),
    )


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def interpolate_route(
    start: tuple[float, float],
    end: tuple[float, float],
    start_time: datetime,
    end_time: datetime,
    num_points: int = 8,
) -> list[dict]:
    """Straight-line GPS trail between two points, evenly spaced in time."""
    points = []
    total_seconds = max((end_time - start_time).total_seconds(), 1)
    for i in range(num_points):
        frac = i / (num_points - 1) if num_points > 1 else 0
        lat = start[0] + (end[0] - start[0]) * frac
        lng = start[1] + (end[1] - start[1]) * frac
        recorded_at = start_time + timedelta(seconds=total_seconds * frac)
        points.append({"lat": lat, "lng": lng, "speed_kmh": round(random.uniform(15, 30), 1), "recorded_at": recorded_at})
    return points


def inject_detour(points: list[dict], detour_offset: tuple[float, float] = (0.015, -0.01)) -> list[dict]:
    """Bends the middle of a route out and back, so total_distance >> straight_line distance."""
    if len(points) < 4:
        return points
    mid = len(points) // 2
    detoured = [dict(p) for p in points]
    detoured[mid]["lat"] += detour_offset[0]
    detoured[mid]["lng"] += detour_offset[1]
    detoured[mid - 1]["lat"] += detour_offset[0] * 0.6
    detoured[mid - 1]["lng"] += detour_offset[1] * 0.6
    return detoured


def inject_stationary_stop(points: list[dict], at_index: int | None = None, minutes: float = 15.0) -> list[dict]:
    """Freezes the rider at one point for `minutes` by pushing every later timestamp forward."""
    if len(points) < 2:
        return points
    idx = at_index if at_index is not None else len(points) // 2
    stalled = [dict(p) for p in points]
    frozen_point = stalled[idx]
    delay = timedelta(minutes=minutes)
    for p in stalled[idx + 1 :]:
        p["recorded_at"] += delay
    stalled.insert(idx + 1, {**frozen_point, "recorded_at": frozen_point["recorded_at"] + delay - timedelta(seconds=30)})
    return stalled


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
