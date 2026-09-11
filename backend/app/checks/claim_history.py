"""CLAIM_HISTORY check — plain code / rules.

Flags accounts with unusual refund claim patterns: too many claims recently, claims that
are always approved (possible lenient-agent exploitation), or unusually varied reasons
(possible serial-claim behaviour).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Case, CheckName, CheckResult

LOOKBACK_DAYS = 90
HIGH_FREQUENCY_THRESHOLD = 3
ALWAYS_APPROVED_MIN_CLAIMS = 2


def run(case: Case) -> CheckResult:
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    recent = [c for c in case.customer_refund_history if c.created_at >= cutoff]

    claims_count = len(recent)
    approved = [c for c in recent if c.outcome in ("approved", "voucher")]
    approved_ratio = (len(approved) / claims_count) if claims_count else 0.0
    reason_diversity = len({c.reason for c in recent})

    risk_flags: list[str] = []
    if claims_count >= HIGH_FREQUENCY_THRESHOLD:
        risk_flags.append("high_frequency")
    if claims_count >= ALWAYS_APPROVED_MIN_CLAIMS and approved_ratio >= 0.99:
        risk_flags.append("always_approved")
    if reason_diversity >= 3 and claims_count >= 3:
        risk_flags.append("varied_reasons")

    risk_score = min(
        0.25 * min(claims_count, 4)
        + (0.2 if "always_approved" in risk_flags else 0.0)
        + (0.15 if "varied_reasons" in risk_flags else 0.0),
        0.95,
    )

    flagged = len(risk_flags) > 0
    confidence = 0.6 + risk_score / 3 if flagged else 0.8

    if flagged:
        summary = (
            f"Customer has {claims_count} claims in the last {LOOKBACK_DAYS} days "
            f"({', '.join(risk_flags)})."
        )
    else:
        summary = f"Customer has {claims_count} claims in the last {LOOKBACK_DAYS} days; no unusual pattern."

    return CheckResult(
        check_name=CheckName.claim_history,
        flagged=flagged,
        confidence=round(min(confidence, 0.99), 2),
        summary=summary,
        details={
            "claims_last_90_days": claims_count,
            "approved_ratio": round(approved_ratio, 2),
            "reason_diversity": reason_diversity,
            "risk_score": round(risk_score, 2),
            "risk_flags": risk_flags,
        },
    )
