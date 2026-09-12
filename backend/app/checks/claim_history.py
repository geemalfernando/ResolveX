"""CLAIM_HISTORY check — calibrated IsolationForest + XGBoost, with rule fallback.

Flags unusual refund patterns. Anomaly alone does not flag when risk is near zero;
risk_score drives the decision so mid-band scores stay meaningful.
"""

from __future__ import annotations

from ..config import get_settings
from ..ml.claim_history_model import LOOKBACK_DAYS, extract_features, predict
from ..models import Case, CheckName, CheckResult

HIGH_FREQUENCY_THRESHOLD = 3
ALWAYS_APPROVED_MIN_CLAIMS = 2
RISK_PROBABILITY_THRESHOLD = 0.55
# IsolationForest can fire on rare-but-legit histories; only use it when risk is elevated.
ANOMALY_RISK_FLOOR = 0.35


def _rule_flags(features: dict[str, float]) -> list[str]:
    flags: list[str] = []
    claims_count = features["claims_last_90_days"]
    if claims_count >= HIGH_FREQUENCY_THRESHOLD:
        flags.append("high_frequency")
    if claims_count >= ALWAYS_APPROVED_MIN_CLAIMS and features["approved_ratio"] >= 0.99:
        flags.append("always_approved")
    if features["reason_diversity"] >= 3 and claims_count >= 3:
        flags.append("varied_reasons")
    return flags


def run(case: Case) -> CheckResult:
    features = extract_features(case.customer_refund_history)
    risk_flags = _rule_flags(features)
    prediction = predict(case.customer_refund_history)

    if prediction:
        risk_score = prediction["risk_probability"]
        anomaly_supports = prediction["anomaly"] and risk_score >= ANOMALY_RISK_FLOOR
        flagged = risk_score >= RISK_PROBABILITY_THRESHOLD or anomaly_supports
        source = prediction["source"]
        confidence = 0.62 + min(risk_score, 0.35) if flagged else 0.86
    else:
        risk_score = min(
            0.25 * min(features["claims_last_90_days"], 4)
            + (0.2 if "always_approved" in risk_flags else 0.0)
            + (0.15 if "varied_reasons" in risk_flags else 0.0),
            0.95,
        )
        flagged = len(risk_flags) > 0
        source = "rules"
        confidence = 0.6 + risk_score / 3 if flagged else 0.8

    claims_count = int(features["claims_last_90_days"])
    threshold = get_settings().claim_history_auto_refund_threshold
    if flagged or risk_score >= threshold:
        summary = (
            f"Customer has {claims_count} claims in the last {LOOKBACK_DAYS} days "
            f"(risk={risk_score:.0%}). Auto-refund held for admin review "
            f"(threshold {threshold:.0%}"
            f"{', ' + ', '.join(risk_flags) if risk_flags else ''})."
        )
    else:
        summary = (
            f"Customer has {claims_count} claims in the last {LOOKBACK_DAYS} days "
            f"(risk={risk_score:.0%}); below {threshold:.0%} so this claim can auto-refund."
        )

    details = {
        "claims_last_90_days": claims_count,
        "approved_ratio": round(features["approved_ratio"], 2),
        "reason_diversity": int(features["reason_diversity"]),
        "risk_score": round(float(risk_score), 2),
        "risk_flags": risk_flags,
        "source": source,
        "auto_refund_eligible": (not flagged) and risk_score < threshold,
        "auto_refund_threshold": threshold,
    }
    if prediction:
        details["anomaly"] = prediction["anomaly"]
        details["anomaly_score"] = prediction["anomaly_score"]
        details["risk_probability"] = prediction["risk_probability"]
        details["risk_probability_raw"] = prediction.get("risk_probability_raw")
        details["probability_temperature"] = prediction.get("probability_temperature")

    return CheckResult(
        check_name=CheckName.claim_history,
        flagged=flagged,
        confidence=round(min(confidence, 0.99), 2),
        summary=summary,
        details=details,
    )
