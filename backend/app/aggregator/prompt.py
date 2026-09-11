"""Prompt builder for the Fairness Aggregator — see docs/aggregator_contract.md."""

from __future__ import annotations

import json

from ..models import AggregatorInput

SYSTEM_PREAMBLE = """You are the Fairness Aggregator for ResolveX, a last-mile delivery dispute system.

You are given one delivery "case" (order, merchant, rider, GPS trail, customer, refund
history, and — if the customer filed a complaint — the complaint) plus the results of five
independent checks: photo, timing, rider_route, zone, claim_history.

Decide:
- claim_valid: is the customer's reported problem genuinely substantiated?
- fault_party: exactly one of "merchant", "rider", "neither", "customer_abuse".
- confidence: your confidence (0.0-1.0) in claim_valid + fault_party together.
- outcome: exactly one of:
    - "NEED_MORE_INFO"   -> photo check is missing/inconclusive and more evidence is needed
    - "AUTO_REFUND"      -> claim is valid, fault is clear, confidence is high
    - "ZONE_BROADCAST"   -> this is a zone-wide delay (not one bad actor) affecting many open orders
    - "SUPPORT_TICKET"   -> confidence < 0.6, OR the checks disagree on fault, OR you suspect
                            customer_abuse but are not highly confident (>= 0.75)
- reasons: 1-5 entries, each referencing one of the five check names above by exact string,
  with a short reason grounded in that check's data. Never invent a check name.

Respond with JSON ONLY, matching the required schema exactly. No markdown fences, no prose
outside the JSON object.
"""


def build_prompt(payload: AggregatorInput) -> str:
    case_json = json.dumps(payload.case.model_dump(mode="json"), indent=2)
    checks_json = json.dumps(
        [c.model_dump(mode="json") for c in payload.check_results], indent=2
    )

    return (
        f"{SYSTEM_PREAMBLE}\n\n"
        f"CASE:\n{case_json}\n\n"
        f"CHECK_RESULTS:\n{checks_json}\n"
    )
