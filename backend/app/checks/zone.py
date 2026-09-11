"""ZONE check — plain code.

If a high percentage of open orders in a zone are late, flags a zone-wide delay
(e.g. a merchant kitchen backlog, rain, or road closure) rather than a single bad actor.
"""

from __future__ import annotations

from ..config import get_settings
from ..models import Case, CheckName, CheckResult


def run(case: Case) -> CheckResult:
    settings = get_settings()
    snapshot = case.zone_snapshot

    late_ratio = (
        snapshot.late_orders_count / snapshot.open_orders_count
        if snapshot.open_orders_count > 0
        else 0.0
    )
    threshold = settings.zone_late_ratio_threshold
    zone_wide_delay = late_ratio >= threshold
    traffic_level = "Jam" if late_ratio >= 0.6 else "High" if late_ratio >= 0.3 else "Medium" if late_ratio > 0 else "Low"

    confidence = min(0.5 + late_ratio, 0.95) if zone_wide_delay else 0.85

    if late_ratio >= 0.5:
        cause_hint = "severe_disruption"
    elif zone_wide_delay:
        cause_hint = "elevated_delay"
    else:
        cause_hint = "none"

    if zone_wide_delay:
        summary = (
            f"{snapshot.late_orders_count}/{snapshot.open_orders_count} open orders "
            f"({late_ratio:.0%}) are late in zone {snapshot.zone_id} — likely zone-wide delay."
        )
    else:
        summary = (
            f"Only {late_ratio:.0%} of open orders are late in zone {snapshot.zone_id}; "
            "no zone-wide pattern."
        )

    return CheckResult(
        check_name=CheckName.zone,
        flagged=zone_wide_delay,
        confidence=round(confidence, 2),
        summary=summary,
        details={
            "zone_id": snapshot.zone_id,
            "open_orders_count": snapshot.open_orders_count,
            "late_orders_count": snapshot.late_orders_count,
            "average_delay_minutes": snapshot.average_delay_minutes,
            "late_ratio": round(late_ratio, 3),
            "threshold": threshold,
            "zone_wide_delay": zone_wide_delay,
            "traffic_level": traffic_level,
            "cause_hint": cause_hint,
            "source": "rules",
        },
    )
