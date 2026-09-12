"""Customer evidence loop, partner review, support mediation and admin feedback."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import checks, workflows as wf
from ..aggregator.aggregator import run_aggregator
from ..auth import AuthPrincipal, require_roles
from ..case_builder import build_case
from ..models import AggregatorInput, CaseResponse
from .cases import get_case

router = APIRouter(tags=["workflow"])


def _claim_signal(payload: dict) -> dict:
    checks_rows = payload.get("workflow", {}).get("checks", []) or []
    check = next((row for row in checks_rows if row.get("check_name") == "claim_history"), None)
    details = (check or {}).get("details", {}) or {}
    risk = float(details.get("risk_score", details.get("risk_probability", 0)) or 0)
    return {
        "risk_score": risk,
        "risk_flags": details.get("risk_flags", []) or [],
        "claims_last_90_days": int(details.get("claims_last_90_days", 0) or 0),
        "flagged": bool((check or {}).get("flagged")),
    }


def _case_record(row: dict) -> dict:
    payload = row["case_payload"]
    return dict(
        case_id=row["id"],
        status=row["status"],
        case=payload,
        verdict=payload.get("workflow", {}).get("verdict"),
        check_results=payload.get("workflow", {}).get("checks", []),
        claim_risk=_claim_signal(payload),
    )


def _list_cases(merchant_id: Optional[str] = None):
    all_rows = wf.rows("cases")
    selected = [
        r for r in all_rows
        if not merchant_id or r["case_payload"]["merchant"]["id"] == merchant_id
    ]
    selected.sort(key=lambda r: r["created_at"], reverse=True)
    return [_case_record(r) for r in selected]


@router.get("/workflow/cases")
def list_cases(principal: AuthPrincipal = Depends(require_roles("partner", "support", "ops", "admin"))):
    merchant_id = principal.merchant_id if principal.role == "partner" else None
    return _list_cases(merchant_id)


@router.get("/workflow/support")
def support_queue(principal: AuthPrincipal = Depends(require_roles("support", "admin"))):
    tickets = [
        row for row in wf.rows("support_tickets")
        if row["status"] in ("open", "in_progress")
    ]
    cases_by_id = {row["id"]: row for row in wf.rows("cases")}
    records = []
    for ticket in tickets:
        row = cases_by_id.get(ticket["case_id"])
        if not row:
            continue
        record = _case_record(row)
        record["ticket"] = ticket
        records.append(record)
    records.sort(key=lambda r: r["ticket"].get("created_at") or "", reverse=True)
    return {
        "count": len(records),
        "cases": records,
    }


class EvidenceBody(BaseModel):
    photo_url: Optional[str] = None
    description: Optional[str] = None


@router.post("/cases/{case_id}/evidence", response_model=CaseResponse)
def add_evidence(
    case_id: str,
    body: EvidenceBody,
    principal: AuthPrincipal = Depends(require_roles("customer", "support", "admin")),
):
    with wf.LOCK:
        current = get_case(case_id)
        if principal.role == "customer" and current.case.customer.id != principal.customer_id:
            raise HTTPException(403, "You can only add evidence to your own cases")
        if current.status == "resolved":
            raise HTTPException(409, "This case is resolved; contact support to reopen it.")
        if not body.photo_url and not body.description:
            raise HTTPException(422, "Add a photo or an explanation.")
        old = current.case
        if not old.complaint:
            raise HTTPException(409, "This proactive incident has no customer complaint.")
        case = build_case(
            order_id=old.order.id,
            trigger=old.trigger,
            complaint_type=old.complaint.type,
            description=body.description or old.complaint.description,
            photo_url=body.photo_url or old.complaint.photo_url,
        )
        case.case_id = old.case_id
        case.complaint.id = old.complaint.id
        case.workflow = old.workflow
        case.workflow.setdefault("additional_evidence", []).append(
            dict(photo_url=body.photo_url, description=body.description, at=wf.now())
        )
        wf.event(case, "Additional customer evidence received")
        wf.get_supabase().table("complaints").update(
            dict(photo_url=case.complaint.photo_url, description=case.complaint.description)
        ).eq("id", case.complaint.id).execute()
        results = checks.run_all(case)
        return wf.persist_analysis(case, results, run_aggregator(AggregatorInput(case=case, check_results=results)))


class PartnerBody(BaseModel):
    action: Literal["accept", "dispute"]
    reason: str = ""


@router.post("/cases/{case_id}/partner")
def partner(
    case_id: str,
    body: PartnerBody,
    principal: AuthPrincipal = Depends(require_roles("partner", "admin")),
):
    with wf.LOCK:
        response = get_case(case_id)
        if principal.role == "partner" and response.case.merchant.id != principal.merchant_id:
            raise HTTPException(403, "This case belongs to another merchant")
        if not response.verdict:
            raise HTTPException(409, "No verdict is available")
        if body.action == "dispute" and not body.reason.strip():
            raise HTTPException(422, "A dispute reason is required")
        case = response.case
        case.workflow["partner"] = dict(
            status="disputed" if body.action == "dispute" else "accepted",
            reason=body.reason,
            at=wf.now(),
            actor_user_id=principal.user_id,
        )
        wf.event(case, "Partner disputed the verdict" if body.action == "dispute" else "Partner accepted the verdict")
        if body.action == "dispute":
            wf.ticket(case)
            case.workflow["resolution_action"] = "SUPPORT_TICKET"
            status = "aggregated"
        else:
            status = response.status
        wf.save_case(case, status)
        return get_case(case_id)


class SupportBody(BaseModel):
    action: Literal["confirm", "merchant", "rider", "neither", "request_evidence", "approve_refund", "reject"]
    reason: str = ""


@router.post("/cases/{case_id}/support")
def support(
    case_id: str,
    body: SupportBody,
    principal: AuthPrincipal = Depends(require_roles("support", "admin")),
):
    with wf.LOCK:
        response = get_case(case_id)
        case, verdict = response.case, response.verdict
        if not verdict:
            raise HTTPException(409, "No assessment available")
        public_model = "NEITHER" if verdict.model_prediction == "EXTERNAL" else (
            verdict.model_prediction or verdict.fault_party.value.upper()
        )
        human = (
            body.action.upper()
            if body.action in ("merchant", "rider", "neither")
            else case.workflow.get("human_verdict", verdict.fault_party.value.upper())
        )
        if human != public_model and not body.reason.strip():
            raise HTTPException(422, "An override reason is required when changing the AI verdict")
        if body.action in ("reject", "request_evidence") and not body.reason.strip():
            raise HTTPException(422, "An explanation is required")
        if body.action == "request_evidence":
            case.workflow["evidence_request"] = body.reason
            case.workflow["resolution_action"] = "NEED_MORE_INFO"
            wf.close_tickets(case, "Waiting for additional evidence")
            wf.event(case, "Support requested more evidence")
            wf.save_case(case, "aggregated")
        else:
            case.workflow["human_verdict"] = human
            case.workflow.setdefault("feedback", []).append(
                dict(
                    case_id=case_id,
                    model_prediction=verdict.model_prediction,
                    model_confidence=verdict.confidence,
                    human_verdict=human,
                    confirmed=human == public_model,
                    override_reason=body.reason,
                    action=body.action,
                    resolved_at=wf.now(),
                    reviewer_user_id=principal.user_id,
                )
            )
            case.workflow.pop("evidence_request", None)
            if body.action == "approve_refund":
                wf.refund(case)
                case.workflow["resolution_action"] = "AUTO_REFUND"
            elif body.action == "reject":
                case.workflow["resolution_action"] = "NO_ACTION"
            else:
                case.workflow["resolution_action"] = "AUTO_REFUND" if case.workflow.get("refund") else "NO_ACTION"
            wf.close_tickets(case, body.reason or "AI verdict confirmed")
            wf.event(case, "Support decision recorded: " + body.action)
            wf.save_case(case, "resolved")
        return get_case(case_id)


@router.get("/notifications")
def notifications(
    customer_id: Optional[str] = None,
    order_id: Optional[str] = None,
    principal: AuthPrincipal = Depends(require_roles("customer", "support", "ops", "admin")),
):
    if order_id:
        orders = wf.rows("orders", id=order_id)
        if not orders:
            raise HTTPException(404, "Order not found")
        customer_id = orders[0]["customer_id"]
    if principal.role == "customer":
        if not principal.customer_id:
            raise HTTPException(403, "Customer account is not linked")
        if customer_id and customer_id != principal.customer_id:
            raise HTTPException(403, "You can only view your own notifications")
        customer_id = principal.customer_id
    if not customer_id:
        raise HTTPException(422, "Supply customer_id or order_id")
    return [
        n
        for row in wf.rows("cases")
        for n in row["case_payload"].get("workflow", {}).get("zone_incident", {}).get("notifications", [])
        if n["customer_id"] == customer_id
    ]


@router.get("/workflow/ops")
def ops(principal: AuthPrincipal = Depends(require_roles("ops", "support", "admin"))):
    orders = wf.rows("orders")
    cases = _list_cases()
    tickets = [r for r in wf.rows("support_tickets") if r["status"] in ("open", "in_progress")]
    zones = [r["case"].get("workflow", {}).get("zone_incident") for r in cases]
    zones = [z for z in zones if z and z.get("active")]
    return dict(
        counts=dict(
            active_orders=sum(o["status"] in wf.OPEN for o in orders),
            late_orders=sum(o["status"] in wf.OPEN and o["is_late_flagged"] for o in orders),
            open_incidents=sum(c["status"] != "resolved" for c in cases),
            zone_incidents=len(zones),
            auto_resolved=sum(bool(c["case"].get("workflow", {}).get("refund")) for c in cases),
            support_review=len(tickets),
        ),
        zone_incidents=zones,
        cases=cases,
        support_case_ids=[t["case_id"] for t in tickets],
    )


@router.get("/workflow/admin")
def admin(principal: AuthPrincipal = Depends(require_roles("admin"))):
    cases, orders, refunds = wf.rows("cases"), wf.rows("orders"), wf.rows("refund_history")
    accounts = []
    for customer in wf.rows("customers"):
        cid = customer["id"]
        customer_cases = [r for r in cases if r["case_payload"]["customer"]["id"] == cid]
        claims = sum(bool(r["case_payload"].get("complaint")) for r in customer_cases)
        signals = [_claim_signal(r["case_payload"]) for r in customer_cases]
        highest = max(signals, key=lambda s: s["risk_score"], default={"risk_score": 0, "risk_flags": [], "claims_last_90_days": 0, "flagged": False})
        accounts.append(
            dict(
                id=cid,
                name=customer["name"],
                orders=sum(o["customer_id"] == cid for o in orders),
                claims=claims,
                refunds=sum(r["customer_id"] == cid for r in refunds),
                manual_review=any(r["case_payload"].get("workflow", {}).get("account_manual_review") for r in customer_cases),
                claim_risk=highest,
            )
        )
    feedback = [f for c in cases for f in c["case_payload"].get("workflow", {}).get("feedback", [])]
    reviewed = {f["case_id"]: f for f in feedback}
    overrides = sum(not f["confirmed"] for f in reviewed.values())
    repeat = {"merchant": {}, "rider": {}}
    for c in cases:
        wf_data = c["case_payload"].get("workflow", {})
        party = wf_data.get("human_verdict", "").lower()
        if party in repeat and c["case_payload"].get(party):
            ident = c["case_payload"][party]["id"]
            repeat[party][ident] = repeat[party].get(ident, 0) + 1
    risk_reviews = [
        dict(
            case_id=c["id"],
            customer=c["case_payload"]["customer"]["name"],
            **_claim_signal(c["case_payload"]),
        )
        for c in cases
        if c["status"] != "resolved" and (_claim_signal(c["case_payload"])["flagged"] or _claim_signal(c["case_payload"])["risk_score"] >= 0.55)
    ]
    return dict(
        refunds=[dict(case_id=c["id"], order_id=c["order_id"], customer=c["case_payload"]["customer"]["name"], **c["case_payload"]["workflow"]["refund"])
                 for c in cases if c["case_payload"].get("workflow", {}).get("refund")],
        fraud_reviews=risk_reviews,
        accounts=accounts,
        reviewed_cases=len(reviewed),
        overrides=overrides,
        agreement_rate=(len(reviewed) - overrides) / len(reviewed) if reviewed else None,
        repeat_faults=repeat,
        feedback=feedback,
    )


class FlagBody(BaseModel):
    manual_review: bool


@router.post("/workflow/admin/customers/{customer_id}")
def flag(
    customer_id: str,
    body: FlagBody,
    principal: AuthPrincipal = Depends(require_roles("admin")),
):
    with wf.LOCK:
        matches = [r for r in wf.rows("cases") if r["case_payload"]["customer"]["id"] == customer_id]
        if not matches:
            raise HTTPException(409, "Account has no case history to flag")
        from ..models import Case
        for row in matches:
            case = Case.model_validate(row["case_payload"])
            case.workflow["account_manual_review"] = body.manual_review
            wf.event(case, "Account manual review flag " + ("enabled" if body.manual_review else "cleared"))
            wf.save_case(case)
    return {"manual_review": body.manual_review}
