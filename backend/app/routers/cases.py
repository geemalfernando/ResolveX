"""POST /cases — build a case from a customer report (or an internal trigger) and run the
full pipeline: Case Builder -> 5 checks -> Fairness Aggregator -> persisted verdict.

GET /cases/{id} — fetch a previously built case with its checks and verdict.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from postgrest.exceptions import APIError

from .. import checks
from ..aggregator.aggregator import run_aggregator
from ..case_builder import build_case
from ..db import get_supabase
from ..models import (
    AggregatorInput,
    CaseResponse,
    CreateCaseRequest,
    Outcome,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/upload-photo")
def upload_photo(file: UploadFile = File(...)) -> dict[str, str]:
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, and WebP images are supported")

    contents = file.file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo must be 10 MB or smaller")

    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[file.content_type]
    path = f"{uuid.uuid4()}.{extension}"
    try:
        sb = get_supabase()
        sb.storage.from_("complaint-photos").upload(
            path,
            contents,
            {"content-type": file.content_type, "upsert": "false"},
        )
        public_url = sb.storage.from_("complaint-photos").get_public_url(path)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Photo upload failed: {exc}") from exc

    return {"photo_url": public_url}


@router.post("", response_model=CaseResponse)
def create_case(body: CreateCaseRequest) -> CaseResponse:
    try:
        case = build_case(
            order_id=body.order_id,
            trigger=body.trigger,
            complaint_type=body.complaint_type,
            description=body.description,
            photo_url=body.photo_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    check_results = checks.run_all(case)
    verdict = run_aggregator(AggregatorInput(case=case, check_results=check_results))

    sb = get_supabase()

    if case.complaint:
        sb.table("complaints").insert(
            {
                "id": case.complaint.id,
                "order_id": case.order.id,
                "customer_id": case.customer.id,
                "type": case.complaint.type.value,
                "description": case.complaint.description,
                "photo_url": case.complaint.photo_url,
            }
        ).execute()

    case_row = (
        sb.table("cases")
        .insert(
            {
                "id": case.case_id,
                "order_id": case.order.id,
                "complaint_id": case.complaint.id if case.complaint else None,
                "trigger": case.trigger.value,
                "case_payload": case.model_dump(mode="json"),
                "status": "open",
            }
        )
        .execute()
    )

    sb.table("check_results").insert(
        [
            {
                "case_id": case.case_id,
                "check_name": cr.check_name.value,
                "result": cr.model_dump(mode="json"),
                "flagged": cr.flagged,
            }
            for cr in check_results
        ]
    ).execute()

    try:
        sb.table("verdicts").insert(
            {
                "case_id": case.case_id,
                "claim_valid": verdict.claim_valid,
                "fault_party": verdict.fault_party.value,
                "confidence": verdict.confidence,
                "outcome": verdict.outcome.value,
                "reasons": [r.model_dump(mode="json") for r in verdict.reasons],
                "raw_llm_response": verdict.model_dump(mode="json"),
            }
        ).execute()
    except APIError as exc:
        migration_needed = exc.code == "23514" and "verdicts_fault_party_check" in exc.message
        detail = (
            "Fault analysis completed, but its verdict could not be saved. Apply the EXTERNAL fault constraint migration."
            if migration_needed else "Fault analysis completed, but its verdict could not be saved."
        )
        raise HTTPException(status_code=503, detail=detail, headers={"X-Case-ID": case.case_id}) from exc

    if verdict.outcome == Outcome.support_ticket:
        sb.table("support_tickets").insert({"case_id": case.case_id, "status": "open"}).execute()

    if verdict.outcome == Outcome.zone_broadcast:
        zone_id = case.order.zone_id
        open_orders = (
            sb.table("orders")
            .select("id, customer_id")
            .eq("zone_id", zone_id)
            .in_("status", ["placed", "preparing", "ready", "picked_up"])
            .execute()
            .data
            or []
        )
        message = (
            "Heads up - deliveries in your area are running behind due to a zone-wide delay. "
            "We're on it and your order is still on the way."
        )
        broadcast_rows = [
            {
                "case_id": case.case_id,
                "zone_id": zone_id,
                "order_id": o["id"],
                "customer_id": o["customer_id"],
                "message": message,
            }
            for o in open_orders
        ]
        if broadcast_rows:
            try:
                sb.table("zone_broadcasts").insert(broadcast_rows).execute()
            except APIError as exc:
                migration_needed = exc.code == "42P01" and "zone_broadcasts" in exc.message
                detail = (
                    "Verdict computed, but the zone-wide broadcast could not be sent. "
                    "Apply supabase/migrations/20260912_zone_broadcasts.sql."
                    if migration_needed
                    else "Verdict computed, but the zone-wide broadcast could not be sent."
                )
                raise HTTPException(status_code=503, detail=detail, headers={"X-Case-ID": case.case_id}) from exc

    sb.table("cases").update({"status": "aggregated"}).eq("id", case.case_id).execute()

    del case_row  # response id already known; row insert result unused beyond error surfacing

    return CaseResponse(
        case_id=case.case_id,
        status="aggregated",
        case=case,
        check_results=check_results,
        verdict=verdict,
    )


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str) -> CaseResponse:
    sb = get_supabase()

    case_row = sb.table("cases").select("*").eq("id", case_id).single().execute().data
    if not case_row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    check_rows = sb.table("check_results").select("*").eq("case_id", case_id).execute().data or []
    try:
        verdict_row = sb.table("verdicts").select("*").eq("case_id", case_id).single().execute().data
    except APIError as exc:
        if exc.code != "PGRST116":
            raise
        verdict_row = None  # Unique case_id means this is a pending/failed save, not duplicates.

    from ..models import Case, CheckResult, FaultParty, Verdict, VerdictReason

    case = Case(**case_row["case_payload"])
    check_results = [CheckResult(**row["result"]) for row in check_rows]
    verdict = None
    if verdict_row:
        verdict = Verdict(
            **{k: v for k, v in (verdict_row.get("raw_llm_response") or {}).items()
               if k in Verdict.model_fields and k not in {"claim_valid", "fault_party", "confidence", "outcome", "reasons"}},
            claim_valid=verdict_row["claim_valid"],
            fault_party=FaultParty(verdict_row["fault_party"]),
            confidence=verdict_row["confidence"],
            outcome=Outcome(verdict_row["outcome"]),
            reasons=[VerdictReason(**r) for r in verdict_row["reasons"]],
        )

    return CaseResponse(
        case_id=case_id,
        status=case_row["status"],
        case=case,
        check_results=check_results,
        verdict=verdict,
    )
