# Refund automation and claim-history screening

Every case analysis records `workflow.fraud_screening`. High-risk or flagged history, unavailable history, and manual-review holds prevent automatic refunds and route otherwise refundable cases to support. Signals indicate suspected abuse, not proven fraud. The configured claim-history model is used when its dependencies are available; the explicit rules fallback is displayed otherwise.

Eligible low-risk claims still use the existing trained fault-model confidence threshold. Completed refunds appear in the customer case and Admin → Automated refunds & fraud screening. Refunds are simulated, cover the order total, and never transfer real money. The existing single-process lock plus an order-based deterministic refund ID and approved-refund lookup prevent duplicate refunds for the same order across cases. Multi-worker transactional payment processing is not implemented.

Admin shows unresolved risk reviews and refund activity; it refreshes every 15 seconds. Support can review and resolve held claims. Resolving a case removes it from the pending risk list.

## Scenario data

The seed refresh preserves Auth users, profiles, and linked customer/merchant IDs. Old recognized Faker and BUSY/ML_VERIFY seed records are replaced after a local backup and a stale-snapshot check. Backups and manifests live in ignored `scripts/seed_output/`; do not commit them.

`refresh_demo_data.py --backup <snapshot>` previews the replacement. `--apply` deletes recognized seed records and creates the scenarios. Stop the backend/demo feed first. The refresh is not a database transaction: retain the backup if a network failure interrupts it.

The 14 named cases cover kitchen delay, rider detour, long stop, far drop-off, zone delay, frequent approved claims, repeated denied claims, damaged/wrong/missing items and broken-seal evidence requests, unrecorded delivery, absent GPS, and an on-time proactive check. Background orders and dated historical refunds provide consistent context. Photo cases intentionally require real evidence uploads; no photo-analysis result is fabricated. Historical orders use past timestamps, refunds reference actual orders, and the active zone scenario includes both late and on-time deliveries.

Live outcomes and IDs are recorded in `scripts/seed_output/scenario_manifest.json`. They come from the real check → model → workflow pipeline, not seeded verdict labels. Exact predictions can change when model artifacts change.
