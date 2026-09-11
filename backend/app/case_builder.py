"""Case Builder — pulls order items, timestamps, rider GPS trail, merchant, and customer
refund history into one Case object. See docs/case_contract.md section 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import TypeAdapter

from .db import get_supabase
from .models import (
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


_timestamp = TypeAdapter(datetime)


def _zone_snapshot(zone_id: str) -> ZoneSnapshot:
    sb = get_supabase()
    open_orders = (
        sb.table("orders")
        .select("id, is_late_flagged, placed_at, promised_delivery_minutes", count="exact")
        .eq("zone_id", zone_id)
        .in_("status", ["placed", "preparing", "ready", "picked_up"])
        .execute()
    )
    rows = open_orders.data or []
    open_count = len(rows)
    late_count = sum(1 for r in rows if r.get("is_late_flagged"))
    now = datetime.now(timezone.utc)
    delays = [max(0, (now - _timestamp.validate_python(r["placed_at"])).total_seconds() / 60 - r["promised_delivery_minutes"])
              for r in rows if r.get("placed_at") and r.get("promised_delivery_minutes") is not None]
    return ZoneSnapshot(zone_id=zone_id, open_orders_count=open_count, late_orders_count=late_count,
                        average_delay_minutes=round(sum(delays) / len(delays), 2) if delays else None)


def build_case(
    order_id: str,
    trigger: CaseTrigger,
    complaint_type: ComplaintType | None = None,
    description: str | None = None,
    photo_url: str | None = None,
) -> Case:
    sb = get_supabase()

    order_row = sb.table("orders").select("*").eq("id", order_id).single().execute().data
    if not order_row:
        raise ValueError(f"Order {order_id} not found")

    merchant_row = sb.table("merchants").select("*").eq("id", order_row["merchant_id"]).single().execute().data
    customer_row = sb.table("customers").select("*").eq("id", order_row["customer_id"]).single().execute().data

    delivery = (order_row.get("items") or [{}])[0].get("delivery")
    if delivery:
        customer_row = {**customer_row, **{k: delivery[k] for k in ("address", "lat", "lng")}}

    rider_row = None
    gps_rows = []
    if order_row.get("rider_id"):
        rider_row = sb.table("riders").select("*").eq("id", order_row["rider_id"]).single().execute().data
        gps_result = (
            sb.table("rider_gps_points")
            .select("*")
            .eq("order_id", order_id)
            .order("recorded_at")
            .execute()
        )
        gps_rows = gps_result.data or []

    refund_result = (
        sb.table("refund_history")
        .select("*")
        .eq("customer_id", order_row["customer_id"])
        .order("created_at", desc=True)
        .execute()
    )
    refund_rows = refund_result.data or []

    complaint_snapshot = None
    if complaint_type is not None:
        # NOTE: the complaint row itself is persisted by routers/cases.py::create_case
        # (alongside the /cases/upload-photo flow) — this just builds the in-memory
        # snapshot with the id that call site will actually insert.
        complaint_snapshot = ComplaintSnapshot(
            id=str(uuid.uuid4()),
            type=complaint_type,
            description=description,
            photo_url=photo_url,
        )

    return Case(
        case_id=str(uuid.uuid4()),
        trigger=trigger,
        order=OrderSnapshot(
            id=order_row["id"],
            status=order_row["status"],
            zone_id=order_row["zone_id"],
            items=[OrderItem(**item) for item in order_row["items"]],
            promised_prep_minutes=order_row["promised_prep_minutes"],
            promised_delivery_minutes=order_row["promised_delivery_minutes"],
            timestamps=OrderTimestamps(
                placed_at=order_row["placed_at"],
                prep_started_at=order_row.get("prep_started_at"),
                ready_at=order_row.get("ready_at"),
                picked_up_at=order_row.get("picked_up_at"),
                dropped_off_at=order_row.get("dropped_off_at"),
            ),
        ),
        merchant=MerchantSnapshot(
            id=merchant_row["id"],
            name=merchant_row["name"],
            zone_id=merchant_row["zone_id"],
            lat=merchant_row["lat"],
            lng=merchant_row["lng"],
            avg_prep_minutes=merchant_row["avg_prep_minutes"],
        ),
        rider=RiderSnapshot(id=rider_row["id"], name=rider_row["name"], vehicle=rider_row["vehicle"])
        if rider_row
        else None,
        rider_gps_trail=[
            GpsPoint(lat=p["lat"], lng=p["lng"], speed_kmh=p.get("speed_kmh"), recorded_at=p["recorded_at"])
            for p in gps_rows
        ],
        customer=CustomerSnapshot(
            id=customer_row["id"],
            name=customer_row["name"],
            address=customer_row["address"],
            lat=customer_row["lat"],
            lng=customer_row["lng"],
        ),
        customer_refund_history=[
            RefundHistoryEntry(
                reason=r["reason"], amount=r["amount"], outcome=r["outcome"], created_at=r["created_at"]
            )
            for r in refund_rows
        ],
        complaint=complaint_snapshot,
        zone_snapshot=_zone_snapshot(order_row["zone_id"]),
    )
