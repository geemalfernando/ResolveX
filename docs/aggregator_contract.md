# ResolveX — Fairness Aggregator Contract

The aggregator uses the local trained fault classifier and then applies resolution
constraints. Gemini is used only for photo evidence. `backend/app/models.py:Verdict`
is the authoritative response schema; old Gemini prompt/schema files are unused.

## Prediction

- `fault_prediction` and `model_prediction` are MERCHANT, RIDER, EXTERNAL or NEITHER
  when ML succeeds; `fault_party` is the lowercase compatibility field.
- `confidence` and `fault_confidence` equal max(predict_proba), not claim validity.
- `class_probabilities` contains all four probabilities in estimator class order.
- `model_used`, `model_name`, `model_version`, `label_provenance`, `feature_names`,
  `features`, `feature_vector` and `fallback_reason` make inference auditable.
- `claim_valid` is currently a compatibility heuristic (predicted party != NEITHER),
  not a separately trained claim-validity assessment.
- `reasons` contains the supplied analyzer summaries.

Fault labels are synthetic/pseudo-labelled incident scenarios derived from public and
synthetic logistics records, not historical fault determinations. Refund history is
excluded from fault features and used separately for claim-risk constraints.

## Resolution precedence

1. Missing photo for damaged/wrong/missing-item complaints: NEED_MORE_INFO.
2. ML unavailable, disputed evidence, inconclusive relevant photo, or claim risk >= 0.5:
   SUPPORT_TICKET.
3. Model confidence below 0.55: NEED_MORE_INFO.
4. Model confidence below 0.85, or NEITHER prediction: SUPPORT_TICKET.
5. EXTERNAL: ZONE_BROADCAST; otherwise AUTO_REFUND.

Thresholds are configurable. None of these rules modifies model probabilities.
Absent photos do not independently block lateness complaints. Fallback confidence
is explicitly an uncalibrated rule score, with model_used=false and empty probabilities.

Full verdict metadata is stored in `verdicts.raw_llm_response` and restored on retrieval.
See [fault_inference.md](fault_inference.md) for dataset provenance, training commands,
feature definitions, actual artifact/API tests, and database migration requirements.

Moderate confidence is 0.55–0.85 by default, configured with
`SUPPORT_REVIEW_CONFIDENCE_THRESHOLD` and `AUTO_ACTION_CONFIDENCE_THRESHOLD`.
Case responses also expose separate top-level `eta`, `fault`, and `resolution`
objects. Failed verdict saves return HTTP 503 with an explicit reason and
`X-Case-ID`; the case remains open and GET returns a null verdict.
