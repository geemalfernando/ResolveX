"""Fairness Aggregator — local decision engine first, Gemini optional.

Gemini can rewrite a nicer reason, but token / quota failures must never blank a
verdict. `_local_decision_engine` covers the demo outcomes on its own.
"""

from __future__ import annotations

from ..config import get_settings
from ..models import (
    AggregatorInput,
    CaseTrigger,
    CheckName,
    CheckResult,
    ComplaintType,
    FaultParty,
    Outcome,
    Verdict,
    VerdictReason,
)
from .prompt import build_prompt
from .schema import VERDICT_JSON_SCHEMA

logger = logging.getLogger(__name__)


def _by_name(payload: AggregatorInput) -> dict[CheckName, CheckResult]:
    return {c.check_name: c for c in payload.check_results}


def _reason(check: CheckName, text: str) -> dict:
    return {"check": check.value, "reason": text}


def _local_decision_engine(payload: AggregatorInput) -> dict:
    checks = _by_name(payload)
    photo = checks.get(CheckName.photo)
    timing = checks.get(CheckName.timing)
    route = checks.get(CheckName.rider_route)
    zone = checks.get(CheckName.zone)
    claims = checks.get(CheckName.claim_history)
    complaint = payload.case.complaint
    trigger = payload.case.trigger

    zone_wide = bool(zone and zone.flagged and zone.details.get("zone_wide_delay"))
    photo_missing = bool(photo and photo.details.get("match") is None)
    photo_damaged = bool(photo and photo.details.get("damage_detected"))
    photo_mismatch = bool(photo and photo.details.get("match") is False)
    high_claim_risk = bool(
        claims and claims.flagged and float(claims.details.get("risk_score") or 0) >= 0.55
    )
    timing_flagged = bool(timing and timing.flagged)
    route_flagged = bool(route and route.flagged)
    corroborating = photo_damaged or photo_mismatch or timing_flagged or route_flagged

    if trigger == CaseTrigger.zone_delay or (zone_wide and complaint is None):
        return {
            "claim_valid": True,
            "fault_party": FaultParty.neither.value,
            "confidence": 0.84,
            "outcome": Outcome.zone_broadcast.value,
            "reasons": [
                _reason(CheckName.zone, zone.summary if zone else "Zone-wide delay detected."),
            ],
        }

    needs_photo = bool(
        complaint
        and complaint.type in {ComplaintType.wrong_item, ComplaintType.damaged, ComplaintType.missing_item}
        and photo_missing
    )
    if needs_photo:
        return {
            "claim_valid": False,
            "fault_party": FaultParty.neither.value,
            "confidence": 0.42,
            "outcome": Outcome.need_more_info.value,
            "reasons": [
                _reason(CheckName.photo, photo.summary if photo else "A photo is required for this complaint."),
            ],
        }

    if high_claim_risk and not corroborating:
        return {
            "claim_valid": False,
            "fault_party": FaultParty.customer_abuse.value,
            "confidence": 0.71,
            "outcome": Outcome.support_ticket.value,
            "reasons": [
                _reason(CheckName.claim_history, claims.summary if claims else "Unusual refund pattern."),
            ],
        }

    if high_claim_risk and corroborating:
        return {
            "claim_valid": True,
            "fault_party": FaultParty.neither.value,
            "confidence": 0.48,
            "outcome": Outcome.support_ticket.value,
            "reasons": [
                _reason(CheckName.claim_history, claims.summary if claims else "High claim risk."),
                _reason(
                    CheckName.photo if photo and photo.flagged else CheckName.timing,
                    "Evidence exists, but claim history makes automatic refund unsafe.",
                ),
            ],
        }

    if photo_damaged or photo_mismatch:
        return {
            "claim_valid": True,
            "fault_party": FaultParty.merchant.value,
            "confidence": 0.82,
            "outcome": Outcome.auto_refund.value,
            "reasons": [
                _reason(CheckName.photo, photo.summary if photo else "Photo does not support the packed order."),
            ],
        }

    if route_flagged and zone_wide:
        return {
            "claim_valid": True,
            "fault_party": FaultParty.neither.value,
            "confidence": 0.52,
            "outcome": Outcome.support_ticket.value,
            "reasons": [
                _reason(CheckName.rider_route, route.summary if route else "Rider route looks abnormal."),
                _reason(CheckName.zone, zone.summary if zone else "Zone is also delayed."),
            ],
        }

    if route_flagged:
        return {
            "claim_valid": True,
            "fault_party": FaultParty.rider.value,
            "confidence": 0.8,
            "outcome": Outcome.auto_refund.value,
            "reasons": [
                _reason(CheckName.rider_route, route.summary if route else "Rider detour or long stop detected."),
            ],
        }

    if timing_flagged:
        stage = timing.details.get("stage_breached") if timing else "none"
        fault = FaultParty.merchant.value if stage == "prep" else FaultParty.rider.value
        if zone_wide:
            fault = FaultParty.neither.value
            outcome = Outcome.zone_broadcast.value if trigger != CaseTrigger.customer_complaint else Outcome.auto_refund.value
            return {
                "claim_valid": True,
                "fault_party": fault,
                "confidence": 0.78,
                "outcome": outcome,
                "reasons": [
                    _reason(CheckName.timing, timing.summary if timing else "Order ran late."),
                    _reason(CheckName.zone, zone.summary if zone else "Delay is zone-wide."),
                ],
            }
        return {
            "claim_valid": True,
            "fault_party": fault,
            "confidence": 0.8,
            "outcome": Outcome.auto_refund.value,
            "reasons": [
                _reason(CheckName.timing, timing.summary if timing else "Promised time was missed."),
            ],
        }

    if complaint and complaint.type == ComplaintType.late and not timing_flagged:
        return {
            "claim_valid": False,
            "fault_party": FaultParty.neither.value,
            "confidence": 0.83,
            "outcome": Outcome.need_more_info.value,
            "reasons": [
                _reason(CheckName.timing, timing.summary if timing else "Order stages were within the promised SLA."),
            ],
        }

    return {
        "claim_valid": False,
        "fault_party": FaultParty.neither.value,
        "confidence": 0.55,
        "outcome": Outcome.support_ticket.value,
        "reasons": [
            _reason(CheckName.timing, "No check produced a clear fault; a human should review the complaint."),
        ],
    }


def _call_gemini(prompt: str) -> dict | None:
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VERDICT_JSON_SCHEMA,
            ),
        )
        return json.loads(response.text)
    except Exception:
        logger.warning("Aggregator call with response_schema failed, retrying without it", exc_info=True)

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception:
        logger.exception("Aggregator Gemini call failed; using local decision engine")
        return None


def _is_fault_disputed(payload: AggregatorInput, verdict_dict: dict) -> bool:
    by_name = _by_name(payload)

    rider_flagged = by_name.get(CheckName.rider_route) and by_name[CheckName.rider_route].flagged
    zone_flagged = by_name.get(CheckName.zone) and by_name[CheckName.zone].flagged
    if rider_flagged and zone_flagged:
        return True

    photo_flagged = by_name.get(CheckName.photo) and by_name[CheckName.photo].flagged
    claim_history_flagged = by_name.get(CheckName.claim_history) and by_name[CheckName.claim_history].flagged
    if photo_flagged and claim_history_flagged and verdict_dict.get("fault_party") != "customer_abuse":
        return True

    return False


def _apply_outcome_overrides(payload: AggregatorInput, verdict_dict: dict) -> dict:
    settings = get_settings()
    confidence = verdict_dict.get("confidence", 0.0)
    outcome = verdict_dict.get("outcome")

    if outcome in {Outcome.need_more_info.value, Outcome.zone_broadcast.value}:
        return verdict_dict

    if confidence < settings.aggregator_confidence_threshold or _is_fault_disputed(payload, verdict_dict):
        verdict_dict["outcome"] = Outcome.support_ticket.value

    if verdict_dict.get("fault_party") == FaultParty.customer_abuse.value and confidence < 0.75:
        verdict_dict["outcome"] = Outcome.support_ticket.value

    return verdict_dict


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
    local_verdict = _local_decision_engine(payload)

    verdict_dict = None
    if settings.gemini_api_key and settings.aggregator_use_gemini:
        verdict_dict = _call_gemini(build_prompt(payload))

    if verdict_dict is None:
        verdict_dict = local_verdict

    verdict_dict = _apply_outcome_overrides(payload, verdict_dict)

    return Verdict(
        claim_valid=verdict_dict["claim_valid"],
        fault_party=FaultParty(verdict_dict["fault_party"]),
        confidence=verdict_dict["confidence"],
        outcome=Outcome(verdict_dict["outcome"]),
        reasons=[VerdictReason(**r) for r in verdict_dict["reasons"]],
    )
