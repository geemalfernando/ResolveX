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
from app import workflows as wf  # noqa: E402
from app.aggregator.aggregator import run_aggregator  # noqa: E402
from app.case_builder import build_case  # noqa: E402
from app.models import AggregatorInput, CaseTrigger, ComplaintType  # noqa: E402

BAND_ORDERS_PATH = Path(__file__).resolve().parent / "seed_output" / "claim_band_orders.json"

# How many customers per band to turn into cases (keeps the UI readable).
PER_BAND = {
    "low": 8,
    "low_mid": 8,
    "mid": 8,
    "high_mid": 6,
    "high": 6,
}

COMPLAINT_BY_BAND = {
    "low": (ComplaintType.late, "Delivery felt a bit slow"),
    "low_mid": (ComplaintType.late, "Arrived later than expected"),
    "mid": (ComplaintType.damaged, "Packaging looked rough"),
    "high_mid": (ComplaintType.wrong_item, "Not sure this matches my order"),
    "high": (ComplaintType.late, "Late again — please refund"),
}


def persist_case(sb, case, check_results, verdict) -> str:
    existing = sb.table("cases").select("id").eq("order_id", case.order.id).execute().data or []
    if existing:
        raise FileExistsError(case.order.id)

    if case.complaint:
        stored_type = {"not_delivered": "late", "tampering": "damaged"}.get(
            case.complaint.type.value, case.complaint.type.value
        )
        sb.table("complaints").insert(
            {
                "id": case.complaint.id,
                "order_id": case.order.id,
                "customer_id": case.customer.id,
                "type": stored_type,
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
            "status": "open",
        }
    ).execute()
    saved = wf.persist_analysis(case, check_results, verdict)
    return saved.verdict.outcome.value


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
    skipped = 0
    for band, limit in PER_BAND.items():
        for row in by_band.get(band, [])[:limit]:
            complaint_type, description = COMPLAINT_BY_BAND[band]
            try:
                case = build_case(
                    order_id=row["order_id"],
                    trigger=CaseTrigger.customer_complaint,
                    complaint_type=complaint_type,
                    description=f"[{band}] {description}",
                    photo_url="https://example.com/demo-claim.jpg",
                )
                check_results = checks.run_all(case)
                verdict = run_aggregator(AggregatorInput(case=case, check_results=check_results))
                outcome = persist_case(sb, case, check_results, verdict)
            except FileExistsError:
                print(f"{band:10} {row['customer_name'][:28]:28}  skip  already has a case")
                skipped += 1
                continue

            claim = next(c for c in check_results if c.check_name.value == "claim_history")
            risk = int(round(float(claim.details.get("risk_score") or 0) * 100))
            print(
                f"{band:10} {row['customer_name'][:28]:28} {risk:5d}  {outcome}"
            )
            created += 1

    print(
        f"\nCreated {created} cases"
        + (f", skipped {skipped} existing" if skipped else "")
        + ". Open /claims as admin: below 40% auto-refunds, 40%+ need a manual refund."
    )


if __name__ == "__main__":
    main()
