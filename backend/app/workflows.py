"""Persist product workflows in the existing cases.case_payload JSONB column.

No schema/admin privileges are needed. This is a single-process demo workflow,
with per-case locking and deterministic refund IDs. Payment processing is mocked.
"""
from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from .config import get_settings
from .db import get_supabase
from .models import Case, CaseResponse, CheckResult, Outcome, Verdict

LOCK = threading.RLock()
OPEN = ["placed", "preparing", "ready", "picked_up"]


def now():
    return datetime.now(timezone.utc).isoformat()


def rows(table, **filters):
    output = []
    offset = 0
    while True:
        query = get_supabase().table(table).select("*").order("id")
        for key, value in filters.items():
            query = query.eq(key, value)
        batch = query.range(offset, offset + 499).execute().data or []
        output.extend(batch)
        if len(batch) < 500:
            return output
        offset += 500


def event(case, label):
    case.workflow.setdefault("timeline", []).append(dict(at=now(), label=label))


def save_case(case, status=None):
    update = {"case_payload": case.model_dump(mode="json")}
    if status:
        update["status"] = status
    get_supabase().table("cases").update(update).eq("id", case.case_id).execute()


def ticket(case):
    existing = rows("support_tickets", case_id=case.case_id)
    if not any(r["status"] in ("open", "in_progress") for r in existing):
        get_supabase().table("support_tickets").insert(dict(case_id=case.case_id, status="open")).execute()


def close_tickets(case, notes):
    get_supabase().table("support_tickets").update(dict(status="resolved", resolved_at=now(), resolution_notes=notes)).eq("case_id", case.case_id).in_("status", ["open", "in_progress"]).execute()


def refund(case):
    if case.workflow.get("refund", {}).get("status") == "completed":
        return case.workflow["refund"]
    refund_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"resolvex/refund/order/{case.order.id}"))
    existing = [r for r in rows("refund_history", order_id=case.order.id) if r["outcome"] == "approved"]
    if existing:
        saved = existing[0]
        record = dict(reference="RFD-" + saved["id"][:8].upper(), amount=float(saved["amount"]), currency="LKR", status="completed", processed_at=saved.get("created_at"), mocked=True)
        case.workflow["refund"] = record
        event(case, "Existing order refund reused; no second refund issued")
        return record
    amount = round(sum(item.qty * item.price for item in case.order.items), 2)
    record = dict(reference="RFD-" + refund_id[:8].upper(), amount=amount, currency="LKR", status="completed", processed_at=now(), mocked=True)
    reason = case.complaint.type.value if case.complaint and case.complaint.type.value in ("late", "wrong_item", "damaged", "missing_item") else "other"
    get_supabase().table("refund_history").upsert(dict(id=refund_id, customer_id=case.customer.id, order_id=case.order.id, reason=reason, amount=amount, outcome="approved"), on_conflict="id").execute()
    case.workflow["refund"] = record
    event(case, "Demo refund completed")
    return record


def broadcast(case):
    # Reuse one zone incident for currently active orders, including late joiners.
    owner = case
    for row in rows("cases"):
        wf = row["case_payload"].get("workflow", {})
        incident = wf.get("zone_incident")
        if incident and incident.get("active") and incident["zone_id"] == case.order.zone_id:
            owner = Case.model_validate(row["case_payload"])
            break
    active = [o for o in rows("orders", zone_id=case.order.zone_id) if o["status"] in OPEN]
    incident = owner.workflow.setdefault("zone_incident", dict(id="ZI-" + owner.case_id[:8], zone_id=case.order.zone_id, active=True, created_at=now(), notifications=[]))
    known = {n["customer_id"] for n in incident["notifications"]}
    for customer_id in {o["customer_id"] for o in active} - known:
        incident["notifications"].append(dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, incident["id"] + customer_id)), customer_id=customer_id,
            order_ids=[o["id"] for o in active if o["customer_id"] == customer_id], created_at=now(),
            message="Multiple deliveries in your area are delayed. Neither merchant nor rider is held responsible for this zone-wide disruption.",
            additional_delay_minutes=case.zone_snapshot.average_delay_minutes))
    incident.update(active_orders=len(active), late_orders=sum(o["is_late_flagged"] for o in active), customers_notified=len(incident["notifications"]))
    if owner.case_id != case.case_id:
        save_case(owner)
        case.workflow["zone_incident_id"] = incident["id"]
    else:
        case.workflow["zone_incident"] = incident
    event(case, f"Zone notice sent to {incident['customers_notified']} customers")


def persist_analysis(case, results, verdict):
    sb = get_supabase()
    history = next((r for r in results if r.check_name.value == "claim_history"), None)
    risk = float(history.details.get("risk_score", 0)) if history else None
    risk_threshold = get_settings().claim_history_auto_refund_threshold
    review_required = (
        history is None
        or history.flagged
        or (risk is not None and risk >= risk_threshold)
        or bool(case.workflow.get("account_manual_review"))
    )
    case.workflow["fraud_screening"] = dict(
        status="review_required" if review_required else "low_risk",
        risk_score=risk, source=history.details.get("source", "unknown") if history else "unavailable",
        signals=history.details.get("risk_flags", []) if history else [],
        claims_last_90_days=history.details.get("claims_last_90_days", 0) if history else None,
        checked_at=now(), summary=history.summary if history else "Claim history unavailable; review required.",
    )
    if review_required and verdict.outcome == Outcome.auto_refund:
        verdict = verdict.model_copy(update={"outcome": Outcome.support_ticket, "resolution": Outcome.support_ticket})
    event(case, "Claim-history screening: review required" if review_required else "Claim-history screening: low risk")
    # The full verdict in case JSON is canonical, including NO_ACTION, which the
    # legacy verdicts.outcome check cannot represent. Other outcomes are mirrored.
    case.workflow.pop("resolution_action", None)
    case.workflow["checks"] = [r.model_dump(mode="json") for r in results]
    case.workflow["verdict"] = verdict.model_dump(mode="json")
    sb.table("check_results").delete().eq("case_id", case.case_id).execute()
    sb.table("check_results").insert([dict(case_id=case.case_id, check_name=r.check_name.value, result=r.model_dump(mode="json"), flagged=r.flagged) for r in results]).execute()
    if verdict.outcome != Outcome.no_action:
        sb.table("verdicts").upsert(dict(case_id=case.case_id, claim_valid=verdict.claim_valid, fault_party=verdict.fault_party.value,
            confidence=verdict.confidence, outcome=verdict.outcome.value, reasons=[r.model_dump(mode="json") for r in verdict.reasons],
            raw_llm_response=verdict.model_dump(mode="json")), on_conflict="case_id").execute()
    else:
        sb.table("verdicts").delete().eq("case_id", case.case_id).execute()
    event(case, "Photo evidence analyzed" if case.complaint and case.complaint.photo_url else "Photo evidence requirement checked")
    event(case, "Delivery evidence analyzed")
    event(case, "AI analysis complete")
    if verdict.outcome == Outcome.auto_refund:
        refund(case)
        close_tickets(case, "Automatically refunded")
    elif verdict.outcome == Outcome.zone_broadcast:
        broadcast(case)
        close_tickets(case, "Zone-wide conditions")
    elif verdict.outcome == Outcome.support_ticket:
        ticket(case)
    elif verdict.outcome == Outcome.need_more_info:
        case.workflow["evidence_request"] = "Upload a photo of the delivered items and outer packaging." if verdict.claim_assessment.get("photo_required") else "Please describe the delivery issue and provide any additional delivery evidence."
        close_tickets(case, "Awaiting customer evidence")
    else:
        close_tickets(case, "No action required")
    if verdict.outcome != Outcome.need_more_info:
        case.workflow.pop("evidence_request", None)
    status = "resolved" if verdict.outcome in (Outcome.auto_refund, Outcome.zone_broadcast, Outcome.no_action) else "aggregated"
    save_case(case, status)
    return CaseResponse(case_id=case.case_id, status=status, case=case, check_results=results, verdict=verdict)


def account_review(customer_id):
    return any(r["case_payload"].get("workflow", {}).get("account_manual_review") for r in rows("cases") if r["case_payload"].get("customer", {}).get("id") == customer_id)
