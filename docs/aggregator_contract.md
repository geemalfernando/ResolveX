# ResolveX — Fairness Aggregator Contract

The aggregator is a **single Gemini 3.6 Flash call** that takes the aggregator input
(section 3 of `case_contract.md`) and must return **strict JSON** matching the schema below.
The backend enforces this shape with a Pydantic model (`backend/app/aggregator/schema.py`) and
Gemini's structured output / response schema feature — never free text.

## Output schema

```jsonc
{
  "claim_valid": true,
  "fault_party": "merchant",       // "merchant" | "rider" | "neither" | "customer_abuse"
  "confidence": 0.87,               // 0.0 - 1.0
  "outcome": "AUTO_REFUND",         // "NEED_MORE_INFO" | "AUTO_REFUND" | "ZONE_BROADCAST" | "SUPPORT_TICKET"
  "reasons": [
    { "check": "photo", "reason": "Customer photo shows fried rice, not the ordered biryani." },
    { "check": "timing", "reason": "Prep took 19 min vs 15 min promised, within normal variance." }
  ]
}
```

### Field rules

- `claim_valid` — true if the customer's reported problem is genuinely substantiated by the
  checks (i.e. not a false/abusive claim).
- `fault_party` — one of exactly four values. `customer_abuse` is used when claim history +
  other checks suggest the claim itself is not credible.
- `confidence` — the model's confidence in `claim_valid` + `fault_party` jointly.
- `reasons` — 1-5 entries, each tied to a specific `check_name` from the input. No reason may
  reference a check that wasn't provided.

### Outcome decision rule (enforced twice: in the prompt AND in backend post-processing)

The backend does **not** trust the model to self-police this — after parsing, it overrides
`outcome` to `SUPPORT_TICKET` if either is true:

```python
if verdict.confidence < 0.6 or is_fault_disputed(verdict):
    verdict.outcome = "SUPPORT_TICKET"
```

Where "fault disputed" means the check results disagree strongly, e.g. `rider_route` flags the
rider while `zone` flags a zone-wide delay (merchant/systemic), or `photo` and `claim_history`
point opposite directions.

Otherwise the mapping is:

| condition                                              | outcome         |
|----------------------------------------------------------|-----------------|
| photo check flagged `match: false` with low confidence, or missing photo | `NEED_MORE_INFO` |
| `claim_valid = true`, single clear `fault_party`, confidence >= 0.6 | `AUTO_REFUND` |
| trigger = `zone_delay` or ZONE check flagged `zone_wide_delay: true` and case is not a single-customer complaint | `ZONE_BROADCAST` |
| confidence < 0.6, or checks disagree, or `fault_party = customer_abuse` with confidence < 0.75 | `SUPPORT_TICKET` |

## Prompt contract

`backend/app/aggregator/prompt.py` builds the prompt. It must:

1. State the four possible outcomes and when each applies (mirrors the table above).
2. Include the full case JSON and all check results verbatim (as JSON, not prose paraphrase).
3. Instruct the model to only use the four `fault_party` values and four `outcome` values.
4. Instruct the model to tie every reason to a `check_name` present in the input.
5. Request JSON-only output matching the schema — no markdown fences, no commentary.

## Storage

The raw parsed verdict is stored in `verdicts` (see `db_schema.md`), with the full raw model
response kept in `raw_llm_response` for debugging/audit during the hackathon demo.
