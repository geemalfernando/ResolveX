"""Order-facing endpoints used by the ops dashboard, the live-feed replay script, and the
zone-wide-delay watcher.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..db import get_supabase
from ..auth import AuthPrincipal, current_user, require_roles
from .commerce import authorize_order

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("")
def list_orders(zone_id: Optional[str] = None, status: Optional[str] = None, principal: AuthPrincipal = Depends(current_user)) -> list[dict]:
    sb = get_supabase()
    query = sb.table("orders").select("*")
    if principal.role == "customer": query = query.eq("customer_id", principal.customer_id or "00000000-0000-0000-0000-000000000000")
    elif principal.role == "partner": query = query.eq("merchant_id", principal.merchant_id)
    elif principal.role == "rider": query = query.eq("rider_id", principal.rider_id)
    if zone_id:
        query = query.eq("zone_id", zone_id)
    if status:
        query = query.eq("status", status)
    return query.execute().data or []


@router.get("/{order_id}")
def get_order(order_id: str, principal: AuthPrincipal = Depends(current_user)) -> dict:
    sb = get_supabase()
    row = sb.table("orders").select("*").eq("id", order_id).single().execute().data
    if not row:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    authorize_order(row, principal)
    return row


class OrderStatusUpdate(BaseModel):
    status: str
    timestamp_field: Optional[str] = None  # e.g. "ready_at", "picked_up_at", "dropped_off_at"
    timestamp_value: Optional[str] = None


@router.patch("/{order_id}/status")
def update_order_status(order_id: str, body: OrderStatusUpdate, principal: AuthPrincipal = Depends(require_roles("ops", "admin"))) -> dict:
    """Used by scripts/replay_feed.py to advance an order through its lifecycle stages."""
    sb = get_supabase()
    update = {"status": body.status}
    if body.timestamp_field and body.timestamp_value:
        update[body.timestamp_field] = body.timestamp_value
    result = sb.table("orders").update(update).eq("id", order_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return result.data[0]


class FlagLateBody(BaseModel):
    is_late_flagged: bool = True


@router.post("/{order_id}/flag-late")
def flag_late(order_id: str, body: FlagLateBody, principal: AuthPrincipal = Depends(require_roles("ops", "admin"))) -> dict:
    """Called by the mocked live order feed BEFORE any complaint arrives, so ops can see
    an order is trending late in real time."""
    sb = get_supabase()
    result = (
        sb.table("orders")
        .update({"is_late_flagged": body.is_late_flagged})
        .eq("id", order_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return result.data[0]



@router.get("/zones/{zone_id}/stats")
def zone_stats(zone_id: str, principal: AuthPrincipal = Depends(require_roles("ops", "support", "admin"))) -> dict:
    sb = get_supabase()
    rows = (
        sb.table("orders")
        .select("id, is_late_flagged")
        .eq("zone_id", zone_id)
        .in_("status", ["placed", "preparing", "ready", "picked_up"])
        .execute()
        .data
        or []
    )
    open_count = len(rows)
    late_count = sum(1 for r in rows if r.get("is_late_flagged"))
    late_ratio = (late_count / open_count) if open_count else 0.0
    return {
        "zone_id": zone_id,
        "open_orders_count": open_count,
        "late_orders_count": late_count,
        "late_ratio": round(late_ratio, 3),
    }
