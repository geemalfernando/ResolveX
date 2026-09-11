"""Strict JSON schema for the Fairness Aggregator's Gemini response.

Mirrors `Verdict` in app/models.py, but expressed as a plain JSON schema dict so it can be
passed directly to Gemini's structured-output config (`response_schema`).
See docs/aggregator_contract.md for the full contract.
"""

VERDICT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_valid": {"type": "boolean"},
        "fault_party": {
            "type": "string",
            "enum": ["merchant", "rider", "neither", "customer_abuse"],
        },
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "outcome": {
            "type": "string",
            "enum": ["NEED_MORE_INFO", "AUTO_REFUND", "ZONE_BROADCAST", "SUPPORT_TICKET"],
        },
        "reasons": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "check": {
                        "type": "string",
                        "enum": ["photo", "timing", "rider_route", "zone", "claim_history"],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["check", "reason"],
            },
        },
    },
    "required": ["claim_valid", "fault_party", "confidence", "outcome", "reasons"],
}
