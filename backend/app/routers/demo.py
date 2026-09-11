"""Single-process, accelerated demo feed; writes real isolated demo orders/cases."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Literal

from .. import workflows as wf
from ..models import CreateCaseRequest, CaseTrigger, Case
from .cases import create_case

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)
STATE = {"running": False, "tick": 0, "orders": [], "error": None, "run_id": None}
STOP = threading.Event()
STAGES = ["CREATED", "PREPARING", "READY", "PICKED_UP", "IN_TRANSIT", "DELIVERED"]


def seed():
    sb = wf.get_supabase()
    run = uuid.uuid4().hex[:8]
    STATE.update(run_id=run, tick=0, orders=[], error=None)
    for scenario in ["MERCHANT", "RIDER", "NEITHER"] + ["EXTERNAL"] * 8:
        ids = [str(uuid.uuid4()) for _ in range(4)]
        merchant, rider, customer, order = ids
        zone = f"BUSY_{run}_{scenario}"
        sb.table("merchants").insert(dict(id=merchant, name=f"Demo kitchen {scenario}", zone_id=zone, address="Demo only", lat=6.9, lng=79.8, avg_prep_minutes=10)).execute()
        sb.table("riders").insert(dict(id=rider, name="Demo rider", phone="0000000000", vehicle="bike", zone_id=zone)).execute()
        sb.table("customers").insert(dict(id=customer, name="Demo customer", email=customer+"@example.invalid", phone="0000000000", address="Demo only", lat=6.91, lng=79.81, zone_id=zone)).execute()
        sb.table("orders").insert(dict(id=order, merchant_id=merchant, rider_id=rider, customer_id=customer, zone_id=zone,
            items=[dict(name="Chicken burger meal", qty=1, price=1850)], status="placed", promised_prep_minutes=10,
            promised_delivery_minutes=30, placed_at=wf.now(), is_late_flagged=False)).execute()
        STATE["orders"].append(dict(id=order, rider_id=rider, customer_id=customer, scenario=scenario, zone_id=zone, stage="CREATED", late=False, case_id=None, complaint_exists=False, eta_minutes=None))


def advance():
    with wf.LOCK:
        if not STATE["orders"]:
            seed()
        STATE["tick"] = min(STATE["tick"] + 1, 5)
        index = STATE["tick"]
        sb = wf.get_supabase()
        current = datetime.now(timezone.utc)
        for order in STATE["orders"]:
            abnormal = order["scenario"] != "NEITHER" and index >= 3
            age = (80 if order["scenario"] in ("RIDER", "EXTERNAL") else 70) if abnormal else index * 4
            placed = current - timedelta(minutes=age)
            stamp = lambda minutes: (placed + timedelta(minutes=minutes)).isoformat()
            prep = 50 if order["scenario"] == "MERCHANT" and abnormal else min(12, age)
            pickup = min(prep + 3, age)
            update = dict(status=["placed", "preparing", "ready", "picked_up", "picked_up", "dropped_off"][index],
                placed_at=stamp(0), prep_started_at=stamp(0), ready_at=stamp(prep) if index >= 2 else None,
                picked_up_at=stamp(pickup) if index >= 3 else None, dropped_off_at=current.isoformat() if index == 5 else None,
                is_late_flagged=abnormal)
            sb.table("orders").update(update).eq("id", order["id"]).execute()
            order.update(stage=STAGES[index], late=abnormal, expected_minutes=30, elapsed_minutes=age)
            if index >= 3:
                trail = [dict(order_id=order["id"], rider_id=order["rider_id"], lat=6.9, lng=79.8, recorded_at=stamp(pickup)),
                         dict(order_id=order["id"], rider_id=order["rider_id"], lat=6.91, lng=79.81, recorded_at=current.isoformat())]
                if order["scenario"] == "RIDER":
                    trail[1:1] = [dict(order_id=order["id"], rider_id=order["rider_id"], lat=6.9, lng=79.8, recorded_at=stamp(40)),
                                  dict(order_id=order["id"], rider_id=order["rider_id"], lat=6.91, lng=79.79, recorded_at=stamp(55))]
                sb.table("rider_gps_points").delete().eq("order_id", order["id"]).execute()
                sb.table("rider_gps_points").insert(trail).execute()
        # Detect after updating the whole zone, before any customer complaint.
        for order in STATE["orders"]:
            if order["late"] and not order["case_id"]:
                response = create_case(CreateCaseRequest(order_id=order["id"], trigger=CaseTrigger.live_feed_late))
                order["case_id"] = response.case_id
                order["eta_minutes"] = response.eta["predicted_minutes"]
        if index == 5:
            STATE["running"] = False
        return STATE


def worker():
    while not STOP.wait(3):
        if STATE["running"]:
            try:
                advance()
            except Exception as exc:
                STATE.update(running=False, error="Demo advance failed: " + type(exc).__name__)
                logger.exception("Demo feed failed")


def start_worker():
    STOP.clear()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()


@router.get("/state")
def state():
    with wf.LOCK:
        return dict(STATE)


class Control(BaseModel):
    action: Literal["start", "pause", "reset", "step"]


@router.post("/control")
def control(body: Control):
    with wf.LOCK:
        if body.action == "pause":
            STATE["running"] = False
        elif body.action == "reset":
            STATE["running"] = False
            for order in STATE["orders"]:
                wf.get_supabase().table("orders").update(dict(status="cancelled", is_late_flagged=False)).eq("id", order["id"]).execute()
                if order["case_id"]:
                    from .cases import get_case
                    case = get_case(order["case_id"]).case
                    if case.workflow.get("zone_incident"):
                        case.workflow["zone_incident"]["active"] = False
                    wf.close_tickets(case, "Demo reset")
                    wf.save_case(case, "resolved")
            STATE.update(tick=0, orders=[], run_id=None, error=None)
        elif body.action == "step":
            return advance()
        else:
            if not STATE["orders"]:
                seed()
            STATE["running"] = True
        return STATE
