"""POST /cases — build a case from a customer report (or an internal trigger) and run the
full pipeline: Case Builder -> 5 checks -> Fairness Aggregator -> persisted verdict.

GET /cases/{id} — fetch a previously built case with its checks and verdict.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

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

    case_row = (
        sb.table("cases")
        .insert(
            {
                "id": case.case_id,
                "order_id": case.order.id,
                "complaint_id": case.complaint.id if case.complaint else None,
                "trigger": case.trigger.value,
                "case_payload": case.model_dump(mode="json"),
                "status": "aggregated",
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

    if verdict.outcome == Outcome.support_ticket:
        sb.table("support_tickets").insert({"case_id": case.case_id, "status": "open"}).execute()

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
    verdict_row = sb.table("verdicts").select("*").eq("case_id", case_id).single().execute().data

    from ..models import Case, CheckResult, FaultParty, Verdict, VerdictReason

    case = Case(**case_row["case_payload"])
    check_results = [CheckResult(**row["result"]) for row in check_rows]
    verdict = None
    if verdict_row:
        verdict = Verdict(
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
