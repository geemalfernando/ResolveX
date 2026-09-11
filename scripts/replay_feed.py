"""Plays back the 'tonight' orders planned by seed_data.py on an accelerated timer,
writing status transitions and GPS points into Supabase as if it were a live delivery feed.

This is the "mocked live order feed" from the spec: it flags orders as late (sets
`is_late_flagged=True`) the moment they breach their promised delivery time, BEFORE any
customer complaint exists — so the ops dashboard lights up first and the ZONE check has
real data by the time a complaint (or the zone-broadcast trigger) comes in.

Run: python scripts/replay_feed.py [--speed 15]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

from common import LIVE_ORDERS_PLAN_PATH, get_client, now_utc

ZONE_LATE_RATIO_THRESHOLD = 0.30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--speed",
        type=float,
        default=15.0,
        help="Simulated-seconds-per-real-second speedup factor (default 15x).",
    )
    return parser.parse_args()


def load_plan() -> dict:
    if not LIVE_ORDERS_PLAN_PATH.exists():
        raise SystemExit(
            f"No plan found at {LIVE_ORDERS_PLAN_PATH}. Run scripts/seed_data.py first."
        )
    with open(LIVE_ORDERS_PLAN_PATH) as f:
        return json.load(f)


def build_event_timeline(plan: dict) -> list[dict]:
    """Flattens every order's stage transitions + GPS points into one globally sorted list."""
    events = []
    for order_id, order_plan in plan.items():
        for stage in order_plan["stages"]:
            events.append(
                {
                    "type": "stage",
                    "order_id": order_id,
                    "zone_id": order_plan["zone_id"],
                    "rider_id": order_plan["rider_id"],
                    "placed_at": datetime.fromisoformat(order_plan["placed_at"]),
                    "promised_delivery_minutes": order_plan["promised_delivery_minutes"],
                    "at": datetime.fromisoformat(stage["at"]),
                    "status": stage["status"],
                    "field": stage["field"],
                }
            )
        for point in order_plan["gps_trail"]:
            events.append(
                {
                    "type": "gps",
                    "order_id": order_id,
                    "rider_id": order_plan["rider_id"],
                    "at": datetime.fromisoformat(point["recorded_at"]),
                    "lat": point["lat"],
                    "lng": point["lng"],
                    "speed_kmh": point["speed_kmh"],
                }
            )
    events.sort(key=lambda e: e["at"])
    return events


def compress_timeline(events: list[dict], speed: float) -> list[dict]:
    """Rewrites each event's `at` as a real wall-clock time, compressed by `speed`x and
    anchored to 'now' so replay always feels live regardless of when seed_data.py ran."""
    if not events:
        return events
    first_at = events[0]["at"]
    replay_start = now_utc() + timedelta(seconds=2)
    for e in events:
        sim_offset = (e["at"] - first_at).total_seconds()
        e["real_at"] = replay_start + timedelta(seconds=sim_offset / speed)
    return events


def main() -> None:
    args = parse_args()
    sb = get_client()
    plan = load_plan()
    events = compress_timeline(build_event_timeline(plan), args.speed)

    print(f"Loaded {len(plan)} orders / {len(events)} events. Speed: {args.speed}x. Starting replay...\n")

    order_flagged: dict[str, bool] = defaultdict(bool)
    zone_open: dict[str, set] = defaultdict(set)
    zone_late: dict[str, set] = defaultdict(set)
    zone_broadcast_fired: set = set()

    # Seed zone_open with every order up front (they're all 'placed' already in Supabase).
    for order_id, order_plan in plan.items():
        zone_open[order_plan["zone_id"]].add(order_id)

    for event in events:
        delay = (event["real_at"] - now_utc()).total_seconds()
        if delay > 0:
            time.sleep(delay)

        order_id = event["order_id"]

        if event["type"] == "gps":
            sb.table("rider_gps_points").insert(
                {
                    "order_id": order_id,
                    "rider_id": event["rider_id"],
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "speed_kmh": event["speed_kmh"],
                    "recorded_at": now_utc().isoformat(),
                }
            ).execute()
            continue

        # Stage event: advance the order's status and stage timestamp.
        sb.table("orders").update(
            {"status": event["status"], event["field"]: now_utc().isoformat()}
        ).eq("id", order_id).execute()
        print(f"[{now_utc():%H:%M:%S}] order {order_id[:8]}  -> {event['status']}")

        if event["status"] == "dropped_off":
            zone_open[event["zone_id"]].discard(order_id)
            continue

        # BEFORE any complaint exists: check if this still-open order has blown its SLA.
        elapsed_minutes = (event["at"] - event["placed_at"]).total_seconds() / 60
        if not order_flagged[order_id] and elapsed_minutes > event["promised_delivery_minutes"]:
            order_flagged[order_id] = True
            zone_late[event["zone_id"]].add(order_id)
            sb.table("orders").update({"is_late_flagged": True}).eq("id", order_id).execute()
            print(f"    \U0001f6a8 flagged LATE (elapsed {elapsed_minutes:.0f}m > promised {event['promised_delivery_minutes']}m)")

            zone_id = event["zone_id"]
            open_count = len(zone_open[zone_id]) or 1
            late_ratio = len(zone_late[zone_id]) / open_count
            if late_ratio >= ZONE_LATE_RATIO_THRESHOLD and zone_id not in zone_broadcast_fired:
                zone_broadcast_fired.add(zone_id)
                print(
                    f"    ⛈️  ZONE-WIDE DELAY in {zone_id}: "
                    f"{len(zone_late[zone_id])}/{open_count} open orders late "
                    f"({late_ratio:.0%}) -> trigger a zone_delay case for a ZONE_BROADCAST demo"
                )

    print("\nReplay complete.")
    print("Late orders by zone:")
    for zone_id, late_orders in zone_late.items():
        print(f"  {zone_id}: {len(late_orders)} flagged late -> {sorted(late_orders)[:3]}...")


if __name__ == "__main__":
    main()
