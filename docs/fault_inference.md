# Dataset-derived ETA and fault inference

## Reproduce locally

All paths come from `backend/app/ml/dataset_config.py`, relative to repository root.
From that root, using the backend environment (scikit-learn 1.5.2):

```sh
.venv/bin/python scripts/download_delivery_datasets.py
.venv/bin/python -m backend.app.ml.check_datasets
.venv/bin/python -m backend.app.ml.prepare_training_data
.venv/bin/python -m backend.app.ml.train_eta_model
.venv/bin/python -m backend.app.ml.train_fault_model
.venv/bin/python -m unittest discover -s backend/tests -v
```

Both CSVs must exist and contain their targets before training starts. Every training
entry point prints raw row counts, columns and targets. Source URLs and SHA-256 hashes
are recorded in `data/processed/dataset_manifest.json` and copied into model metadata.
Raw/generated CSVs and binary models stay local and are gitignored; download/training
scripts and JSON metadata make the artifacts reproducible on another machine.

| Source | Local path | Raw rows | ETA target |
| --- | --- | ---: | --- |
| [Zomato](https://github.com/Parth-Malik/Zomato-Delivery-Time-Prediction) | `data/external/zomato/Zomato Dataset.csv` | 45,584 | `Time_taken (min)` |
| [Kaggle synthetic](https://www.kaggle.com/datasets/dharmendrapandit12/food-delivery-time-prediction-dataset) | `data/external/synthetic_food_delivery/Food_Delivery_Time_Prediction.csv` | 50,000 | `Time_taken_min` |

The Kaggle dataset is the input to the user-supplied notebook. It was downloaded from
its public dataset API. The Zomato CSV was copied from the existing local checkout.
Neither source supplies historical fault labels.

## Training and evaluation

`prepare_training_data.py` writes 95,584 normalized operational records. It harmonizes
weather, traffic and vehicle categories and explicitly retains distance/prep basis.
Zomato straight-line distance and order-to-pickup time are imperfect proxies for
Kaggle road distance and preparation duration. Unknown observations remain missing;
preprocessors learn imputation/encoding only from the training split.

ETA uses `distance_km, prep_time_min, order_hour, is_weekend, weather, traffic, vehicle`.
The source-stratified 80/20 split uses seed 17. Held-out ETA MAE:

| Source | MAE (minutes) |
| --- | ---: |
| Zomato | 5.3372 |
| Kaggle synthetic | 3.7174 |

Fault augmentation samples 3,000 source rows per source/partition and generates four
scenarios per row, yielding 24,000 training and 24,000 test incidents. Every row keeps
`source_dataset`, `source_row_id`, `split`, `scenario`, and `label_origin`. The expected
ETA, source delivery time, prep, distance and conditions inform scenario severity.
Noise includes 7% alternate labels, 15% mixed evidence, and 8% missing observations
on selected features. All variants of a source row remain in its original partition.
The ETA model used during augmentation was fitted only on operational training rows.

The fault classifier is a fitted RandomForestClassifier pipeline with imputation.
Its held-out accuracy is 90.975% and log loss is 0.3833 **on generated scenarios**.
This measures reproduction of simulated scenarios, not real fault accuracy. Probability
calibration and accuracy on adjudicated incidents have not been established.
`fault_model_metadata.json`, the API and UI all state this label provenance.
Claim history remains a separate rule-based risk input to resolution; there is no
trained fraud model. Photo evidence controls evidence requirements, not fault labels.

## Exact fault feature order and runtime definitions

The shared `FAULT_FEATURES` constant is used by training and inference. Loading checks
bundle order/count against the fitted estimator. Missing measurements reach the fitted
imputer as NaN and are returned as JSON null in the exact input vector.

| Feature | Definition |
| --- | --- |
| prep_delay_min | Actual prep duration minus promised prep minutes |
| pickup_delay_min | Nonnegative ready-to-pickup minutes |
| travel_delay_min | Actual pickup-to-dropoff duration minus max(0, ETA minus promised prep); promised delivery replaces ETA only if ETA inference is unavailable |
| route_deviation_km | Nonnegative GPS path distance minus endpoint straight-line distance |
| stationary_time_min | Longest observed stationary stretch |
| zone_late_percentage | Zone late ratio multiplied by 100 |
| zone_average_delay_min | Mean nonnegative elapsed-minus-promised delay over open zone orders with timestamps; null when unavailable |

Live ETA uses merchant average prep, straight-line distance, and zone late ratio as a
traffic proxy. Actual weather is unavailable and supplied as `unknown`, not fabricated
sunny weather. These live/source differences remain documented model limitations.

## Actual request trace

`routers/cases.py:create_case` -> `checks.run_all` -> timing calls cached ETA `predict`
-> `aggregator/aggregator.py:run_aggregator` -> `ml/fault_model.py:extract_features`
-> `FaultModel.infer` -> actual classifier `predict(frame)` and `predict_proba(frame)`
-> business constraints -> response and persisted verdict.

FastAPI lifespan loads both models once per process. Defaults are
`backend/app/ml/eta_model.joblib` and `backend/app/ml/fault_model.joblib`; override
with `ETA_MODEL_PATH` and `FAULT_MODEL_PATH`. Restart an existing API process after
retraining. `GET /api/model/status` reports both loaded states, model types, versions,
feature schemas, fault classes, label provenance, ETA metrics and loading errors.

Verdicts retain the old `confidence`, `fault_party` and `outcome` fields and additionally
expose `model_used`, model metadata, `model_prediction`, `fault_prediction`,
`fault_confidence`, all `class_probabilities`, `feature_names`, `features`,
`feature_vector`, `label_provenance`, `fallback_reason`, and `resolution`.
Confidence is exactly max(predict_proba), without rounding or business-rule replacement.
A failed/missing model explicitly falls back with empty probabilities and cannot trigger
an automatic refund/broadcast. Missing photos only require more information for
photo-relevant complaints. Otherwise resolution uses confidence, claim risk and disputes.

## API verification using saved trained artifacts

`backend/tests/test_trained_models.py` calls POST /cases through FastAPI TestClient,
using the actual saved ETA and fault estimators. It asserts both classifier methods,
the ETA method, exact feature order, model_used=true and four different confidences.
Only database access and case loading are mocked; these are constructed incident
cases, not production customer cases. Full inputs/probabilities/resolutions are saved
in `data/processed/api_model_verification.json`.

| Incident scenario | Prediction | Model confidence | Resolution |
| --- | --- | ---: | --- |
| Merchant prep delay | MERCHANT | 83.9987% | SUPPORT_TICKET |
| Rider stationary stop | RIDER | 56.9565% | SUPPORT_TICKET |
| Zone disruption | EXTERNAL | 88.7168% | ZONE_BROADCAST |
| Normal delivery | NEITHER | 80.2372% | SUPPORT_TICKET |

These values are observed outputs, not acceptance thresholds or forced confidences.
The rider case demonstrates that predicted responsibility and resolution are separate.
Enable INFO logging for `backend.app.ml.fault_model` (or `app.ml.fault_model` when running
from backend) to log exact input features and probabilities on every successful call.

## Database compatibility

Full metadata is stored in the existing `raw_llm_response` JSON column and restored
by GET /cases/{id}. Legacy rows explicitly report no recorded ML inference.
Apply `supabase/migrations/20260912_external_fault.sql` to an existing database before
persisting EXTERNAL verdicts. The new-database schema includes EXTERNAL already.
No remote database migration was applied as part of local training/testing.


## Live database and browser integration verification

The backend was restarted on port 8000 with both saved models loaded and no loading
fallback reasons. Model status now also has nested `eta_model` and `fault_model`
objects. Responses have separate top-level `eta`, `fault`, and `resolution` objects.
The UI displays confidence level, exact percentages, human-readable resolution,
ETA prediction and observed evidence. Saved cases can be opened with `/?case=<id>`.

Thirteen backend tests and the frontend production build pass. Real POST /cases
requests were executed against the configured Supabase database, using isolated
`ML_VERIFY_*` zones and clearly labelled demo customers/merchants/orders. No database
mocks were used for these live checks. Test records remain available for inspection.
Reports include both the initial run and latest case IDs.

MERCHANT, RIDER and NEITHER passed persistence, direct DB comparison, GET round-trip,
support-ticket persistence, and headless Chrome rendering checks. EXTERNAL inference
succeeded but persistence failed: PostgreSQL error `23514` explicitly named
`verdicts_fault_party_check`. REST schema inspection confirmed `fault_party` is text,
not an enum. The failed save now returns HTTP 503 with a migration explanation and
case ID, remains open, and its frontend page explicitly reports no saved verdict.

The verified migration is `supabase/migrations/20260912_external_fault.sql`.
It inspects the column type and existing constraint before changing it atomically.
It has **not been applied**: no `DATABASE_URL` or `SUPABASE_ACCESS_TOKEN` is configured.
Authorization to apply it was provided; the remaining blocker is SQL/admin credentials.
The available Supabase table API key cannot execute SQL schema changes.

Once SQL access is configured locally, run:

```sh
.venv/bin/python scripts/apply_external_fault_migration.py
.venv/bin/python scripts/verify_live_integration.py
NODE_PATH=/tmp/resolvex-browser/node_modules node scripts/verify_frontend.cjs
```

The migration helper supports a privileged `DATABASE_URL` via psql or a management
token via the [Supabase SQL API](https://supabase.com/docs/reference/api/v1-run-a-query).
Browser verification uses Playwright (`npm install --prefix /tmp/resolvex-browser playwright`)
and installed Chrome; `CHROME_PATH` can override its location.

### Rider ambiguity diagnosis

The original scenario's probabilities remain RIDER 56.96%, NEITHER 27.96%, MERCHANT
7.79%, EXTERNAL 7.30%. It has 25 stationary minutes but **zero route deviation**.
Generated training rider scenarios generally combine both signals (minimum observed
route deviation 0.305 km; median 2.458 km). This is a scenario-generation limitation.
It does not justify increasing reported confidence. The resolution threshold now sends
this moderate result to support review; automatic action still requires 0.85.

Held-out rider confusion: 5,548 correct, 138 predicted MERCHANT, 144 EXTERNAL,
and 136 NEITHER, from 5,966 pseudo-labelled rider examples (recall 92.99%).
`scripts/analyze_rider_confidence.py` records these diagnostics and feature sensitivity
without modifying the model. The live rider scenario additionally has an observed
detour, as requested, so its different probabilities reflect different evidence.

Detailed artifacts:
- `data/processed/live_integration_verification.json`: live status, case IDs, exact
  vectors/probabilities, DB comparisons, HTTP failure and browser results.
- `data/processed/rider_confidence_analysis.json`: original rider probabilities,
  confusion counts and diagnostic sensitivity.
- Browser screenshots: `/tmp/resolvex-browser/{merchant,rider,neither}.png`.

### Latest live probabilities

| Case | MERCHANT | RIDER | EXTERNAL | NEITHER | Persistence / browser |
| --- | ---: | ---: | ---: | ---: | --- |
| MERCHANT | 83.54% | 2.32% | 2.96% | 11.19% | Passed |
| RIDER | 4.56% | 84.04% | 3.48% | 7.92% | Passed |
| EXTERNAL | 2.11% | 5.09% | 89.00% | 3.80% | Blocked by DB constraint; probabilities are unsaved inference |
| NEITHER | 13.70% | 3.47% | 2.94% | 79.89% | Passed |
