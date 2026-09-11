"""TIMING check — plain code.

Compares promised vs actual duration at each stage (prep, pickup->dropoff) and flags
whichever stage breached its SLA the most.
"""

from __future__ import annotations

from ..models import Case, CheckName, CheckResult


def _minutes_between(start, end) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 60.0


def run(case: Case) -> CheckResult:
    ts = case.order.timestamps

    prep_minutes = _minutes_between(ts.prep_started_at, ts.ready_at)
    delivery_minutes = _minutes_between(ts.placed_at, ts.dropped_off_at)

    prep_promised = case.order.promised_prep_minutes
    delivery_promised = case.order.promised_delivery_minutes

    prep_delay = (prep_minutes - prep_promised) if prep_minutes is not None else 0.0
    delivery_delay = (
        (delivery_minutes - delivery_promised) if delivery_minutes is not None else 0.0
    )

    stage_breached = "none"
    if delivery_delay >= 10 and delivery_delay >= prep_delay:
        stage_breached = "delivery"
    elif prep_delay >= 5:
        stage_breached = "prep"

    flagged = stage_breached != "none"

    worst_delay = max(prep_delay, delivery_delay, 0.0)
    confidence = min(0.5 + worst_delay / 60.0, 0.99) if flagged else 0.9

    if stage_breached == "delivery":
        summary = (
            f"Delivery took {delivery_minutes:.0f} min vs {delivery_promised} min promised "
            f"(+{delivery_delay:.0f} min late)."
        )
    elif stage_breached == "prep":
        summary = (
            f"Prep took {prep_minutes:.0f} min vs {prep_promised} min promised "
            f"(+{prep_delay:.0f} min late)."
        )
    else:
        summary = "Order stages were within promised SLAs."

    return CheckResult(
        check_name=CheckName.timing,
        flagged=flagged,
        confidence=round(confidence, 2),
        summary=summary,
        details={
            "prep_minutes": round(prep_minutes, 1) if prep_minutes is not None else None,
            "prep_promised_minutes": prep_promised,
            "prep_delay_minutes": round(prep_delay, 1),
            "delivery_minutes": round(delivery_minutes, 1) if delivery_minutes is not None else None,
            "delivery_promised_minutes": delivery_promised,
            "delivery_delay_minutes": round(delivery_delay, 1),
            "stage_breached": stage_breached,
        },
    )
