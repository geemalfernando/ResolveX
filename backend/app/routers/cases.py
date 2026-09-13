"""POST /cases — build a case from a customer report (or an internal trigger) and run the
full pipeline: Case Builder -> 5 checks -> Fairness Aggregator -> persisted verdict.

GET /cases/{id} — fetch a previously built case with its checks and verdict.
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from postgrest.exceptions import APIError

from ..auth import AuthPrincipal, current_user, require_roles
from .commerce import find_order, authorize_order
from ..evidence import save_upload
from .. import checks
from ..aggregator.aggregator import run_aggregator
from ..case_builder import build_case
from ..db import get_supabase
from ..models import (
    AggregatorInput,
    CaseResponse,
    CreateCaseRequest,
)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/upload-photo")
def upload_photo(
    file: UploadFile = File(...),
    order_id: str | None = Form(default=None),
    principal: AuthPrincipal = Depends(require_roles("customer", "support", "admin")),
) -> dict[str, str]:
    if not order_id:
        raise HTTPException(status_code=422, detail="Order ID is required so the claim photo can be stored with packing and handover evidence")
    authorize_order(find_order(order_id), principal)
    saved = save_upload(order_id, "claim", file, uploaded_by=principal.user_id)
    return {"photo_url": saved["path"], "path": saved["path"], "signed_url": saved.get("signed_url")}


@router.post("", response_model=CaseResponse)
def submit_case(body: CreateCaseRequest, principal: AuthPrincipal = Depends(require_roles("customer", "support", "ops", "admin"))):
    authorize_order(find_order(body.order_id), principal)
    if principal.role == "customer":
        if not body.complaint_type:
            raise HTTPException(422, "Select a complaint type")
        body.trigger = "customer_complaint"
    return create_case(body)


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
def view_case(case_id: str, principal: AuthPrincipal = Depends(current_user)):
    record = get_case(case_id)
    authorize_order(find_order(record.case.order.id), principal)
    return record


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
    try:
        from ..evidence import evidence_payload
        photos = evidence_payload(case.order.id)
        case.evidence.packing_path = (photos.get("packing") or {}).get("path") or case.evidence.packing_path
        case.evidence.handover_path = (photos.get("handover") or {}).get("path") or case.evidence.handover_path
        case.evidence.claim_path = (photos.get("claim") or {}).get("path") or case.evidence.claim_path
        case.evidence.packing_url = (photos.get("packing") or {}).get("signed_url")
        case.evidence.handover_url = (photos.get("handover") or {}).get("signed_url")
        case.evidence.claim_url = (photos.get("claim") or {}).get("signed_url")
    except Exception:
        pass
    return CaseResponse(case_id=case_id, status=row["status"], case=case, check_results=results, verdict=verdict)
