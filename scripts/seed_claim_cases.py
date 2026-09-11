"""Create ResolveX cases across claim-risk bands so Ops / Support / Claim Risk UI

show real CLAIM HISTORY · AI scores (low → mid → high) without filing each complaint
by hand.

Reads scripts/seed_output/claim_band_orders.json from seed_data.py, runs the same
pipeline as POST /cases (case builder → checks → aggregator), and persists results.

Run after seeding:
  python scripts/seed_data.py --reset
  python scripts/seed_claim_cases.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PHOTO_USE_GEMINI", "false")
os.environ.setdefault("AGGREGATOR_USE_GEMINI", "false")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import get_client  # noqa: E402

from app import checks  # noqa: E402
from app.aggregator.aggregator import run_aggregator  # noqa: E402
from app.case_builder import build_case  # noqa: E402
from app.models import AggregatorInput, CaseTrigger, ComplaintType, Outcome  # noqa: E402

BAND_ORDERS_PATH = Path(__file__).resolve().parent / "seed_output" / "claim_band_orders.json"

# How many customers per band to turn into cases (keeps the UI readable).
PER_BAND = {
    "low": 3,
    "low_mid": 3,
    "mid": 4,
    "high_mid": 3,
    "high": 4,
}

COMPLAINT_BY_BAND = {
    "low": (ComplaintType.late, "Delivery felt a bit slow"),
    "low_mid": (ComplaintType.late, "Arrived later than expected"),
    "mid": (ComplaintType.damaged, "Packaging looked rough"),
    "high_mid": (ComplaintType.wrong_item, "Not sure this matches my order"),
    "high": (ComplaintType.late, "Late again — please refund"),
}


def persist_case(sb, case, check_results, verdict) -> None:
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

    sb.table("cases").insert(
        {
            "id": case.case_id,
            "order_id": case.order.id,
            "complaint_id": case.complaint.id if case.complaint else None,
            "trigger": case.trigger.value,
            "case_payload": case.model_dump(mode="json"),
            "status": "aggregated",
        }
    ).execute()

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


def main() -> None:
    if not BAND_ORDERS_PATH.exists():
        raise SystemExit(
            f"Missing {BAND_ORDERS_PATH}. Run: python scripts/seed_data.py --reset"
        )

    labeled = json.loads(BAND_ORDERS_PATH.read_text())
    by_band: dict[str, list[dict]] = {}
    for row in labeled:
        by_band.setdefault(row["band"], []).append(row)

    sb = get_client()
    print("Creating claim-risk demo cases…\n")
    print(f"{'band':10} {'customer':28} {'risk%':>5}  outcome")

    created = 0
    for band, limit in PER_BAND.items():
        for row in by_band.get(band, [])[:limit]:
            complaint_type, description = COMPLAINT_BY_BAND[band]
            case = build_case(
                order_id=row["order_id"],
                trigger=CaseTrigger.customer_complaint,
                complaint_type=complaint_type,
                description=f"[{band}] {description}",
                photo_url="https://example.com/demo-claim.jpg",
            )
            check_results = checks.run_all(case)
            verdict = run_aggregator(AggregatorInput(case=case, check_results=check_results))
            persist_case(sb, case, check_results, verdict)

            claim = next(c for c in check_results if c.check_name.value == "claim_history")
            risk = int(round(float(claim.details.get("risk_score") or 0) * 100))
            print(
                f"{band:10} {row['customer_name'][:28]:28} {risk:5d}  {verdict.outcome.value}"
            )
            created += 1

    print(f"\nCreated {created} cases. Open /claims, /ops, and /support in the UI.")


if __name__ == "__main__":
    main()
