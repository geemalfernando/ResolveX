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
    from .. import workflows as wf
    with wf.LOCK:
        try:
            case = build_case(order_id=body.order_id, trigger=body.trigger,
                              complaint_type=body.complaint_type, description=body.description, photo_url=body.photo_url)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        case.workflow["account_manual_review"] = wf.account_review(case.customer.id)
        wf.event(case, "Complaint received" if case.complaint else "Incident detected before any complaint")
        sb = get_supabase()
        if case.complaint:
            stored_type = {"not_delivered": "late", "tampering": "damaged"}.get(case.complaint.type.value, case.complaint.type.value)
            sb.table("complaints").insert(dict(id=case.complaint.id, order_id=case.order.id, customer_id=case.customer.id,
                type=stored_type, description=case.complaint.description, photo_url=case.complaint.photo_url)).execute()
        sb.table("cases").insert(dict(id=case.case_id, order_id=case.order.id, complaint_id=case.complaint.id if case.complaint else None,
            trigger=case.trigger.value, case_payload=case.model_dump(mode="json"), status="open")).execute()
        check_results = checks.run_all(case)
        verdict = run_aggregator(AggregatorInput(case=case, check_results=check_results))
        try:
            return wf.persist_analysis(case, check_results, verdict)
        except APIError as exc:
            raise HTTPException(status_code=503, detail="Analysis could not be fully saved; please contact support.", headers={"X-Case-ID": case.case_id}) from exc


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(case_id: str) -> CaseResponse:
    from ..models import Case, CheckResult, Verdict
    sb = get_supabase()
    found = sb.table("cases").select("*").eq("id", case_id).execute().data or []
    if not found:
        raise HTTPException(status_code=404, detail="Case not found")
    row = found[0]
    case = Case.model_validate(row["case_payload"])
    workflow = case.workflow
    if workflow.get("verdict"):
        results = [CheckResult.model_validate(r) for r in workflow.get("checks", [])]
        verdict = Verdict.model_validate(workflow["verdict"])
    else:
        check_rows = sb.table("check_results").select("*").eq("case_id", case_id).execute().data or []
        results = [CheckResult.model_validate(r["result"]) for r in check_rows]
        verdict_rows = sb.table("verdicts").select("*").eq("case_id", case_id).execute().data or []
        verdict = None
        if verdict_rows:
            saved = verdict_rows[0]
            raw = saved.get("raw_llm_response") or saved
            raw = {k: v for k, v in raw.items() if k in Verdict.model_fields}
            if raw.get("fault_party") in ("external", "customer_abuse"):
                raw["cause_category"] = raw["fault_party"].upper()
                raw["fault_party"] = "neither"
                raw["fault_prediction"] = "NEITHER"
            verdict = Verdict.model_validate(raw)
    return CaseResponse(case_id=case_id, status=row["status"], case=case, check_results=results, verdict=verdict)
