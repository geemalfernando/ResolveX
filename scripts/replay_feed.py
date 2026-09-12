"""Replay the seeded busy evening as a live delivery feed.

The data itself is produced by ``scripts/seed_data.py`` and includes merchants,
orders with stage timestamps, rider GPS trails, and customer refund histories.
This replay advances the just-placed "tonight" orders on an accelerated clock,
flags late deliveries before a complaint exists, and can automatically move a
severely delayed order to another rider in the same zone.

Run:
    python scripts/seed_data.py
    python scripts/replay_feed.py --speed 15

Useful demo options:
    --reassign-after 8     minutes beyond SLA before rider reassignment
    --no-auto-reassign     keep the old feed behaviour
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

from common import LIVE_ORDERS_PLAN_PATH, get_client, now_utc

ZONE_LATE_RATIO_THRESHOLD = 0.30
DEFAULT_REASSIGN_AFTER_MINUTES = 8.0
FINAL_STATUS = "dropped_off"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--speed",
        type=float,
        default=15.0,
        help="Simulated-seconds-per-real-second speedup factor (default 15x).",
    )
    parser.add_argument(
        "--reassign-after",
        type=float,
        default=DEFAULT_REASSIGN_AFTER_MINUTES,
        help="Minutes beyond promised delivery before automatic rider reassignment (default 8).",
    )
    parser.add_argument(
        "--no-auto-reassign",
        action="store_true",
        help="Disable the rider-reassignment stretch feature.",
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
    """Flatten every order's stage transitions and GPS points into one timeline."""
    events: list[dict] = []
    for order_id, order_plan in plan.items():
        shared = {
            "order_id": order_id,
            "zone_id": order_plan["zone_id"],
            "placed_at": datetime.fromisoformat(order_plan["placed_at"]),
            "promised_delivery_minutes": order_plan["promised_delivery_minutes"],
        }
        for stage in order_plan["stages"]:
            events.append(
                {
                    **shared,
                    "type": "stage",
                    "at": datetime.fromisoformat(stage["at"]),
                    "status": stage["status"],
                    "field": stage["field"],
                }
            )
        for point in order_plan["gps_trail"]:
            events.append(
                {
                    **shared,
                    "type": "gps",
                    "at": datetime.fromisoformat(point["recorded_at"]),
                    "lat": point["lat"],
                    "lng": point["lng"],
                    "speed_kmh": point["speed_kmh"],
                }
            )
    events.sort(key=lambda e: e["at"])
    return events


def compress_timeline(events: list[dict], speed: float) -> list[dict]:
    """Anchor the simulated evening to now and compress it by ``speed``."""
    if not events:
        return events
    if speed <= 0:
        raise SystemExit("--speed must be greater than zero")
    first_at = events[0]["at"]
    replay_start = now_utc() + timedelta(seconds=2)
    for event in events:
        simulated_offset = (event["at"] - first_at).total_seconds()
        event["real_at"] = replay_start + timedelta(seconds=simulated_offset / speed)
    return events


def load_riders(sb) -> dict[str, dict]:
    rows = sb.table("riders").select("id,name,zone_id").execute().data or []
    return {str(row["id"]): row for row in rows}


def rider_loads(current_rider: dict[str, str], order_status: dict[str, str]) -> dict[str, int]:
    loads: dict[str, int] = defaultdict(int)
    for order_id, rider_id in current_rider.items():
        if order_status.get(order_id) != FINAL_STATUS:
            loads[rider_id] += 1
    return loads


def choose_replacement_rider(
    riders: dict[str, dict],
    current_rider_id: str,
    zone_id: str,
    loads: dict[str, int],
) -> str | None:
    """Choose the least-loaded alternative rider in the same zone."""
    candidates = [
        rider_id
        for rider_id, rider in riders.items()
        if rider_id != current_rider_id and rider.get("zone_id") == zone_id
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda rider_id: (loads.get(rider_id, 0), rider_id))


def record_reassignment(
    sb,
    *,
    order_id: str,
    from_rider_id: str,
    to_rider_id: str,
    zone_id: str,
    minutes_behind: float,
) -> None:
    """Persist an audit row when the migration is installed; replay remains usable without it."""
    try:
        sb.table("rider_reassignments").insert(
            {
                "order_id": order_id,
                "from_rider_id": from_rider_id,
                "to_rider_id": to_rider_id,
                "zone_id": zone_id,
                "reason": "sla_breach_auto_rebalance",
                "minutes_behind": round(minutes_behind, 2),
                "created_at": now_utc().isoformat(),
            }
        ).execute()
    except Exception as exc:
        print(f"    ⚠️ reassignment audit not persisted ({exc})")


def maybe_reassign(
    sb,
    *,
    event: dict,
    riders: dict[str, dict],
    current_rider: dict[str, str],
    order_status: dict[str, str],
    already_reassigned: set[str],
    threshold_minutes: float,
) -> dict | None:
    """Move a severely delayed open order to the least-loaded same-zone rider."""
    order_id = event["order_id"]
    if order_id in already_reassigned or order_status.get(order_id) == FINAL_STATUS:
        return None

    elapsed_minutes = (event["at"] - event["placed_at"]).total_seconds() / 60
    minutes_behind = elapsed_minutes - float(event["promised_delivery_minutes"])
    if minutes_behind < threshold_minutes:
        return None

    old_rider = current_rider.get(order_id)
    if not old_rider:
        return None

    loads = rider_loads(current_rider, order_status)
    new_rider = choose_replacement_rider(riders, old_rider, event["zone_id"], loads)
    if not new_rider:
        print(
            f"    ↪ no spare rider in {event['zone_id']} for order {order_id[:8]} "
            f"({minutes_behind:.0f}m behind)"
        )
        already_reassigned.add(order_id)
        return None

    sb.table("orders").update({"rider_id": new_rider}).eq("id", order_id).execute()
    current_rider[order_id] = new_rider
    already_reassigned.add(order_id)
    record_reassignment(
        sb,
        order_id=order_id,
        from_rider_id=old_rider,
        to_rider_id=new_rider,
        zone_id=event["zone_id"],
        minutes_behind=minutes_behind,
    )

    old_name = riders.get(old_rider, {}).get("name", old_rider[:8])
    new_name = riders.get(new_rider, {}).get("name", new_rider[:8])
    print(
        f"    🔁 AUTO-REASSIGN {order_id[:8]}: {old_name} → {new_name} "
        f"({minutes_behind:.0f}m behind SLA; new rider load={loads.get(new_rider, 0)})"
    )
    return {
        "order_id": order_id,
        "from_rider_id": old_rider,
        "to_rider_id": new_rider,
        "minutes_behind": minutes_behind,
    }


def main() -> None:
    args = parse_args()
    if args.reassign_after < 0:
        raise SystemExit("--reassign-after cannot be negative")

    sb = get_client()
    plan = load_plan()
    events = compress_timeline(build_event_timeline(plan), args.speed)
    riders = load_riders(sb)

    print(
        f"Loaded {len(plan)} orders / {len(events)} events. Speed: {args.speed}x. "
        f"Auto-reassign: {'off' if args.no_auto_reassign else f'on after {args.reassign_after:g}m behind'}.\n"
    )

    order_flagged: dict[str, bool] = defaultdict(bool)
    order_status: dict[str, str] = {order_id: "placed" for order_id in plan}
    current_rider: dict[str, str] = {
        order_id: str(order_plan["rider_id"]) for order_id, order_plan in plan.items()
    }
    already_reassigned: set[str] = set()
    reassignments: list[dict] = []
    zone_open: dict[str, set] = defaultdict(set)
    zone_late: dict[str, set] = defaultdict(set)
    zone_broadcast_fired: set[str] = set()

    for order_id, order_plan in plan.items():
        zone_open[order_plan["zone_id"]].add(order_id)

    for event in events:
        delay = (event["real_at"] - now_utc()).total_seconds()
        if delay > 0:
            time.sleep(delay)

        order_id = event["order_id"]
        rider_id = current_rider[order_id]

        if event["type"] == "gps":
            sb.table("rider_gps_points").insert(
                {
                    "order_id": order_id,
                    "rider_id": rider_id,
                    "lat": event["lat"],
                    "lng": event["lng"],
                    "speed_kmh": event["speed_kmh"],
                    "recorded_at": now_utc().isoformat(),
                }
            ).execute()
        else:
            order_status[order_id] = event["status"]
            sb.table("orders").update(
                {"status": event["status"], event["field"]: now_utc().isoformat()}
            ).eq("id", order_id).execute()
            print(f"[{now_utc():%H:%M:%S}] order {order_id[:8]}  -> {event['status']}")

            if event["status"] == FINAL_STATUS:
                zone_open[event["zone_id"]].discard(order_id)

        if order_status[order_id] == FINAL_STATUS:
            continue

        # Proactive SLA detection is evaluated for every feed event, not only stage changes.
        elapsed_minutes = (event["at"] - event["placed_at"]).total_seconds() / 60
        if not order_flagged[order_id] and elapsed_minutes > event["promised_delivery_minutes"]:
            order_flagged[order_id] = True
            zone_late[event["zone_id"]].add(order_id)
            sb.table("orders").update({"is_late_flagged": True}).eq("id", order_id).execute()
            print(
                f"    🚨 flagged LATE (elapsed {elapsed_minutes:.0f}m > "
                f"promised {event['promised_delivery_minutes']}m)"
            )

            zone_id = event["zone_id"]
            open_count = len(zone_open[zone_id]) or 1
            late_ratio = len(zone_late[zone_id]) / open_count
            if late_ratio >= ZONE_LATE_RATIO_THRESHOLD and zone_id not in zone_broadcast_fired:
                zone_broadcast_fired.add(zone_id)
                print(
                    f"    ⛈️  ZONE-WIDE DELAY in {zone_id}: "
                    f"{len(zone_late[zone_id])}/{open_count} open orders late "
                    f"({late_ratio:.0%}) -> zone broadcast condition reached"
                )

        if not args.no_auto_reassign:
            moved = maybe_reassign(
                sb,
                event=event,
                riders=riders,
                current_rider=current_rider,
                order_status=order_status,
                already_reassigned=already_reassigned,
                threshold_minutes=args.reassign_after,
            )
            if moved:
                reassignments.append(moved)

    print("\nReplay complete.")
    print("Late orders by zone:")
    for zone_id, late_orders in zone_late.items():
        print(f"  {zone_id}: {len(late_orders)} flagged late -> {sorted(late_orders)[:3]}...")
    print(f"Automatic rider reassignments: {len(reassignments)}")
    for item in reassignments[:10]:
        print(
            f"  {item['order_id'][:8]}  {item['from_rider_id'][:8]} -> "
            f"{item['to_rider_id'][:8]}  ({item['minutes_behind']:.0f}m behind)"
        )


if __name__ == "__main__":
    main()
