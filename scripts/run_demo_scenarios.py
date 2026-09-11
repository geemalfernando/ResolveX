"""Run the six competition demo cases locally — no Supabase and no Gemini required.

Uses the trained claim-history / route models plus the local fairness engine.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PHOTO_USE_GEMINI", "false")
os.environ.setdefault("AGGREGATOR_USE_GEMINI", "false")
sys.path.insert(0, str(ROOT / "backend"))

from app.aggregator.aggregator import run_aggregator  # noqa: E402
from app.checks import run_all  # noqa: E402
from app.models import (  # noqa: E402
    AggregatorInput,
    Case,
    CaseTrigger,
    ComplaintSnapshot,
    ComplaintType,
    CustomerSnapshot,
    GpsPoint,
    MerchantSnapshot,
    OrderItem,
    OrderSnapshot,
    OrderTimestamps,
    RefundHistoryEntry,
    RiderSnapshot,
    ZoneSnapshot,
)


NOW = datetime.now(timezone.utc)


def _ts(**minutes: int) -> OrderTimestamps:
    placed = NOW - timedelta(hours=2)
    return OrderTimestamps(
        placed_at=placed,
        prep_started_at=placed + timedelta(minutes=minutes.get("prep_start", 1)),
        ready_at=placed + timedelta(minutes=minutes.get("ready", 16)),
        picked_up_at=placed + timedelta(minutes=minutes.get("pickup", 20)),
        dropped_off_at=placed + timedelta(minutes=minutes.get("dropoff", 38)),
    )


def _base_case(**overrides: object) -> Case:
    case = Case(
        case_id="demo",
        trigger=CaseTrigger.customer_complaint,
        order=OrderSnapshot(
            id="order-demo",
            status="dropped_off",
            zone_id="ZONE_A",
            items=[OrderItem(name="Mixed Vegetables", qty=1, price=420)],
            promised_prep_minutes=15,
            promised_delivery_minutes=35,
            timestamps=_ts(),
        ),
        merchant=MerchantSnapshot(
            id="m1",
            name="Green Basket",
            zone_id="ZONE_A",
            lat=6.9271,
            lng=79.8612,
            avg_prep_minutes=15,
        ),
        rider=RiderSnapshot(id="r1", name="Kasun P.", vehicle="bike"),
        rider_gps_trail=_normal_trail(),
        customer=CustomerSnapshot(
            id="c1",
            name="Amaya S.",
            address="12 Galle Rd, Colombo",
            lat=6.9150,
            lng=79.8500,
        ),
        customer_refund_history=[],
        complaint=ComplaintSnapshot(
            id="comp1",
            type=ComplaintType.late,
            description="Arrived late",
            photo_url="https://example.com/demo.jpg",
        ),
        zone_snapshot=ZoneSnapshot(zone_id="ZONE_A", open_orders_count=12, late_orders_count=1),
    )
    return case.model_copy(update=overrides)


def _normal_trail() -> list[GpsPoint]:
    start = NOW - timedelta(minutes=80)
    points = [
        (6.9271, 79.8612, 18.0, 0),
        (6.9255, 79.8596, 22.0, 4),
        (6.9238, 79.8580, 24.0, 8),
        (6.9220, 79.8564, 23.0, 12),
        (6.9202, 79.8548, 21.0, 16),
        (6.9184, 79.8532, 20.0, 20),
        (6.9166, 79.8516, 16.0, 24),
        (6.9151, 79.8501, 10.0, 28),
    ]
    return [
        GpsPoint(lat=lat, lng=lng, speed_kmh=speed, recorded_at=start + timedelta(minutes=mins))
        for lat, lng, speed, mins in points
    ]


def _detour_trail() -> list[GpsPoint]:
    start = NOW - timedelta(minutes=90)
    points = [
        (6.9271, 79.8612, 0.0, 0),
        (6.9245, 79.8588, 18.0, 6),
        (6.9400, 79.8450, 5.0, 14),
        (6.9401, 79.8451, 0.0, 32),
        (6.9188, 79.8534, 16.0, 40),
        (6.9150, 79.8500, 8.0, 48),
    ]
    return [
        GpsPoint(lat=lat, lng=lng, speed_kmh=speed, recorded_at=start + timedelta(minutes=mins))
        for lat, lng, speed, mins in points
    ]


def _abusive_history() -> list[RefundHistoryEntry]:
    return [
        RefundHistoryEntry(
            reason=reason,
            amount=520,
            outcome="approved",
            created_at=NOW - timedelta(days=days),
        )
        for reason, days in [("late", 4), ("wrong_item", 9), ("damaged", 16), ("missing_item", 22)]
    ]


def scenarios() -> dict[str, Case]:
    return {
        "clear_late_delivery": _base_case(
            order=_base_case().order.model_copy(
                update={"timestamps": _ts(ready=18, pickup=22, dropoff=72)}
            ),
            complaint=ComplaintSnapshot(
                id="late",
                type=ComplaintType.late,
                description="Delivery was very late",
                photo_url="https://example.com/late.jpg",
            ),
        ),
        "damaged_vegetables": _base_case(
            complaint=ComplaintSnapshot(
                id="dmg",
                type=ComplaintType.damaged,
                description="Vegetables crushed",
                photo_url="https://example.com/damaged.jpg",
            )
        ),
        "wrong_item": _base_case(
            complaint=ComplaintSnapshot(
                id="wrong",
                type=ComplaintType.wrong_item,
                description="Got fried rice instead",
                photo_url="https://example.com/wrong.jpg",
            )
        ),
        "high_claim_customer": _base_case(
            customer_refund_history=_abusive_history(),
            complaint=ComplaintSnapshot(
                id="abuse",
                type=ComplaintType.late,
                description="Late again",
                photo_url="https://example.com/late.jpg",
            ),
        ),
        "rider_long_stop": _base_case(
            rider_gps_trail=_detour_trail(),
            order=_base_case().order.model_copy(
                update={"timestamps": _ts(ready=16, pickup=20, dropoff=68)}
            ),
            complaint=ComplaintSnapshot(
                id="route",
                type=ComplaintType.late,
                description="Rider stopped for a long time",
                photo_url="https://example.com/late.jpg",
            ),
        ),
        "normal_order": _base_case(),
        "zone_wide_delay": _base_case(
            trigger=CaseTrigger.zone_delay,
            complaint=None,
            zone_snapshot=ZoneSnapshot(zone_id="ZONE_B", open_orders_count=10, late_orders_count=8),
            order=_base_case().order.model_copy(update={"zone_id": "ZONE_B", "timestamps": _ts(dropoff=70)}),
        ),
    }


def main() -> None:
    print("ResolveX local demo — trained models + local fairness engine\n")
    for name, case in scenarios().items():
        results = run_all(case)
        verdict = run_aggregator(AggregatorInput(case=case, check_results=results))
        flagged = ", ".join(f"{c.check_name.value}={c.flagged}" for c in results)
        print(f"{name:22} -> {verdict.outcome.value:16} fault={verdict.fault_party.value:15}  {flagged}")
        print(f"{'':22}    {verdict.reasons[0].reason}")


if __name__ == "__main__":
    main()
