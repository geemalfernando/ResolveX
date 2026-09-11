"""Operational fault inference and separate claim/risk resolution decisions."""
from __future__ import annotations

from ..config import get_settings
from ..ml.fault_model import fault_model
from ..models import AggregatorInput, CheckName, ComplaintType, FaultParty, Outcome, Verdict, VerdictReason

PHOTO_RELEVANT_COMPLAINTS = {ComplaintType.damaged, ComplaintType.wrong_item, ComplaintType.missing_item, ComplaintType.tampering}


def _rule_fallback(payload):
    checks = {c.check_name: c for c in payload.check_results}
    if checks.get(CheckName.zone) and checks[CheckName.zone].flagged:
        return "EXTERNAL", 0.8
    timing = checks.get(CheckName.timing)
    if timing and timing.details.get("prep_delay_minutes", 0) >= 5:
        return "MERCHANT", 0.55
    if checks.get(CheckName.rider_route) and checks[CheckName.rider_route].flagged:
        return "RIDER", 0.55
    return "NEITHER", 0.4


def assess_claim(payload):
    case = payload.case
    evidence = {c.check_name: c for c in payload.check_results}
    photo = evidence.get(CheckName.photo)
    timing = evidence.get(CheckName.timing)
    history = evidence.get(CheckName.claim_history)
    risk = history.details.get("risk_score", 1) if history else 1
    if case.workflow.get("account_manual_review"):
        risk = 1
    complaint = case.complaint
    photo_required = bool(complaint and complaint.type in PHOTO_RELEVANT_COMPLAINTS)
    missing = photo_required and not complaint.photo_url
    if missing:
        supported = None
        reason = "A photo of the delivered items and outer packaging is required."
    elif photo_required:
        supported = photo.details.get("complaint_supported") if photo else None
        reason = "Photo evidence supports this complaint." if supported else "Photo evidence is inconclusive or does not support the complaint; review is needed."
    elif complaint and complaint.type == ComplaintType.not_delivered:
        supported = case.order.timestamps.dropped_off_at is None
        reason = "No drop-off has been recorded." if supported else "Delivery is recorded; support should review the non-delivery report."
    elif timing:
        supported = timing.details.get("delivery_delay_minutes", 0) > 0 or timing.flagged
        reason = timing.summary
    else:
        supported, reason = None, "Timing evidence is unavailable."
    return dict(supported=supported, photo_required=photo_required, missing_required_photo=missing,
                risk_score=risk, risk_level="HIGH" if risk >= 0.5 else "LOW", reason=reason)


def run_aggregator(payload: AggregatorInput) -> Verdict:
    inference = fault_model.infer(payload)
    if inference["model_used"]:
        prediction = inference["model_prediction"]
        confidence = max(inference["class_probabilities"].values())
    else:
        prediction, confidence = _rule_fallback(payload)
    public_party = "NEITHER" if prediction == "EXTERNAL" else prediction
    claim = assess_claim(payload)
    settings = get_settings()
    checks = {c.check_name: c for c in payload.check_results}
    zone = checks.get(CheckName.zone)
    disputed = payload.case.workflow.get("partner", {}).get("status") == "disputed"
    if claim["missing_required_photo"]:
        outcome = Outcome.need_more_info
    elif disputed or claim["risk_score"] >= 0.5 or not inference["model_used"]:
        outcome = Outcome.support_ticket
    elif prediction == "EXTERNAL" and zone and zone.flagged:
        outcome = Outcome.zone_broadcast
    elif claim["supported"] and confidence >= settings.auto_action_confidence_threshold and payload.case.complaint:
        outcome = Outcome.auto_refund
    elif not payload.case.complaint and not any(c.flagged for c in payload.check_results):
        outcome = Outcome.no_action
    elif confidence < settings.support_review_confidence_threshold:
        outcome = Outcome.need_more_info
    else:
        outcome = Outcome.support_ticket
    reasons = [VerdictReason(check=c.check_name, reason=c.summary) for c in payload.check_results]
    if prediction == "EXTERNAL":
        reasons.append(VerdictReason(check=CheckName.zone, reason="Neither merchant nor rider is held responsible: evidence indicates zone-wide external conditions."))
    return Verdict(claim_valid=claim["supported"] is True, claim_assessment=claim,
        fault_party=FaultParty(public_party.lower()), cause_category=prediction,
        confidence=confidence, fault_confidence=confidence, fault_prediction=public_party,
        outcome=outcome, resolution=outcome, reasons=reasons, **inference)
