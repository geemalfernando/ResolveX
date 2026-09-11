"""Fairness Aggregator — single Gemini 2.5 Flash call + backend post-processing.

STUB: wire up your GEMINI_API_KEY in .env and replace `_call_gemini` below.
The backend never trusts the model's `outcome` blindly — `_apply_outcome_overrides`
always re-checks the confidence threshold and fault-dispute rule server-side.
See docs/aggregator_contract.md.
"""

from __future__ import annotations

import json

from ..config import get_settings
from ..models import (
    AggregatorInput,
    CheckName,
    FaultParty,
    Outcome,
    Verdict,
    VerdictReason,
)
from .prompt import build_prompt
from .schema import VERDICT_JSON_SCHEMA


def _call_gemini(prompt: str) -> dict:
    """
    TODO: replace with a real call to Gemini 2.5 Flash, e.g.:

        from google import genai
        client = genai.Client(api_key=get_settings().gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": VERDICT_JSON_SCHEMA,
            },
        )
        return json.loads(response.text)

    Left as a stub so the rest of the pipeline runs end-to-end before the Gemini key
    is wired up. Returns a plausible placeholder verdict derived from which checks flagged.
    """
    return None  # signals the caller to fall back to the heuristic stub below


def _heuristic_stub_verdict(payload: AggregatorInput) -> dict:
    """Deterministic placeholder used until Gemini is wired up, so /cases works end-to-end."""
    flagged = [c for c in payload.check_results if c.flagged]

    if not flagged:
        return {
            "claim_valid": False,
            "fault_party": "neither",
            "confidence": 0.85,
            "outcome": "SUPPORT_TICKET",
            "reasons": [
                {"check": "timing", "reason": "No checks flagged an issue; needs human review of the complaint."}
            ],
        }

    zone_flagged = any(c.check_name == CheckName.zone and c.flagged for c in payload.check_results)
    if zone_flagged:
        return {
            "claim_valid": True,
            "fault_party": "neither",
            "confidence": 0.8,
            "outcome": "ZONE_BROADCAST",
            "reasons": [{"check": "zone", "reason": "A high share of open orders in this zone are late."}],
        }

    photo_result = next((c for c in payload.check_results if c.check_name == CheckName.photo), None)
    if photo_result and photo_result.details.get("match") is None:
        return {
            "claim_valid": False,
            "fault_party": "neither",
            "confidence": 0.4,
            "outcome": "NEED_MORE_INFO",
            "reasons": [{"check": "photo", "reason": "No photo was submitted with this complaint."}],
        }

    fault = "merchant" if any(c.check_name == CheckName.timing and c.flagged for c in payload.check_results) else "rider"
    return {
        "claim_valid": True,
        "fault_party": fault,
        "confidence": 0.7,
        "outcome": "AUTO_REFUND",
        "reasons": [{"check": c.check_name.value, "reason": c.summary} for c in flagged[:5]],
    }


def _is_fault_disputed(payload: AggregatorInput, verdict_dict: dict) -> bool:
    """Rough heuristic: rider_route and zone both flag (rider vs systemic), or photo and
    claim_history point opposite directions (genuine damage vs suspected abuse)."""
    by_name = {c.check_name: c for c in payload.check_results}

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

    if confidence < settings.aggregator_confidence_threshold or _is_fault_disputed(payload, verdict_dict):
        verdict_dict["outcome"] = Outcome.support_ticket.value

    if verdict_dict.get("fault_party") == FaultParty.customer_abuse.value and confidence < 0.75:
        verdict_dict["outcome"] = Outcome.support_ticket.value

    return verdict_dict


def run_aggregator(payload: AggregatorInput) -> Verdict:
    settings = get_settings()
    prompt = build_prompt(payload)

    verdict_dict = None
    if settings.gemini_api_key:
        verdict_dict = _call_gemini(prompt)

    if verdict_dict is None:
        verdict_dict = _heuristic_stub_verdict(payload)

    verdict_dict = _apply_outcome_overrides(payload, verdict_dict)

    return Verdict(
        claim_valid=verdict_dict["claim_valid"],
        fault_party=FaultParty(verdict_dict["fault_party"]),
        confidence=verdict_dict["confidence"],
        outcome=Outcome(verdict_dict["outcome"]),
        reasons=[VerdictReason(**r) for r in verdict_dict["reasons"]],
    )
