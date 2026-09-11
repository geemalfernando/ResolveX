"""Evidence -> trained fault classifier -> business constraints -> resolution."""
from __future__ import annotations

from ..config import get_settings
from ..ml.fault_model import fault_model
from ..models import AggregatorInput, CheckName, ComplaintType, FaultParty, Outcome, Verdict, VerdictReason

PHOTO_RELEVANT_COMPLAINTS = {ComplaintType.damaged, ComplaintType.wrong_item, ComplaintType.missing_item}


def _rule_fallback(payload: AggregatorInput) -> tuple[str, float]:
    """Explicit, uncalibrated fallback only when trained inference is unavailable."""
    checks = {c.check_name: c for c in payload.check_results}
    if checks.get(CheckName.zone) and checks[CheckName.zone].flagged:
        return "EXTERNAL", 0.8
    timing = checks.get(CheckName.timing)
    if timing and timing.details.get("prep_delay_minutes", 0) >= 5:
        return "MERCHANT", 0.55
    if checks.get(CheckName.rider_route) and checks[CheckName.rider_route].flagged:
        return "RIDER", 0.55
    return "NEITHER", 0.4


def run_aggregator(payload: AggregatorInput) -> Verdict:
    inference = fault_model.infer(payload)
    if inference["model_used"]:
        prediction = inference["model_prediction"]
        confidence = max(inference["class_probabilities"].values())
    else:
        prediction, confidence = _rule_fallback(payload)

    settings = get_settings()
    checks = {c.check_name: c for c in payload.check_results}
    complaint = payload.case.complaint
    photo = checks.get(CheckName.photo)
    history = checks.get(CheckName.claim_history)
    photo_required = complaint is not None and complaint.type in PHOTO_RELEVANT_COMPLAINTS
    photo_missing = photo_required and not complaint.photo_url
    photo_inconclusive = photo_required and (photo is None or photo.details.get("match") is None)
    risk = history.details.get("risk_score", 1) if history else 1
    disputed = (
        bool(checks.get(CheckName.zone) and checks[CheckName.zone].flagged
             and checks.get(CheckName.rider_route) and checks[CheckName.rider_route].flagged)
        or bool(photo and photo.flagged and history and history.flagged)
    )
    # Constraints never overwrite the classifier's prediction or probability.
    if photo_missing:
        outcome = Outcome.need_more_info
    elif not inference["model_used"] or disputed or photo_inconclusive or risk >= 0.5:
        outcome = Outcome.support_ticket
    elif confidence < settings.support_review_confidence_threshold:
        outcome = Outcome.need_more_info
    elif confidence < settings.auto_action_confidence_threshold or prediction == "NEITHER":
        outcome = Outcome.support_ticket
    elif prediction == "EXTERNAL":
        outcome = Outcome.zone_broadcast
    else:
        outcome = Outcome.auto_refund
    reasons = [VerdictReason(check=c.check_name, reason=c.summary) for c in payload.check_results]
    return Verdict(
        claim_valid=prediction != "NEITHER", fault_party=FaultParty(prediction.lower()),
        confidence=confidence, fault_confidence=confidence, fault_prediction=prediction,
        outcome=outcome, resolution=outcome, reasons=reasons, **inference,
    )
