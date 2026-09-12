# Recent branch integration

Integration branch: `integration-recent-work`. Original branches and both stashes were left intact. No remote branch was pushed or rewritten.

The requested 45-minute window was anchored at 2026-09-11 21:43:40 UTC
(2026-09-12 03:13:40 Asia/Colombo), beginning at 20:58:40 UTC.
Commits by geemal1976@gmail.com within that window, reachable from the requested branches:

| Commit | Local time | Change |
| --- | --- | --- |
| 8fd1424 | 02:34:14 | Backup code: ETA/fault artifacts and all four CSV datasets |
| 8ba2115 | 02:47:23 | Surface claim-risk board inside Admin |
| 4d89a90 | 02:47:38 | Product wording for Admin claim risk |
| 67faedf | 02:48:00 | Merge claim-risk changes into dev |

Branch spelling on GitHub is `feature/admin-claim-risk`.

The integration starts from local `dev` at c6411a9 (including its 17 login/RBAC
commits), merges `origin/dev` at 67faedf, then `origin/dev-geemal` at 8fd1424.
`origin/feature/admin-claim-risk` is already an ancestor of origin/dev, so its
changes are included without duplicate cherry-picks. Earlier commits required by
these branch tips are included too, including route/claim model training additions.

## Conflict resolution

- Preserve role-aware login, protected routes and server-protected Ops map.
- Add `/claims` as an admin-only route and preserve the embedded Admin claim panel.
- Preserve Ops demo controls and add the remote branch's live case/outcome feed.
- Send claim-board detail/refund actions through the authenticated API helper;
  refund review now uses the existing support workflow rather than disconnected
  zero-amount client-side refund writes.
- Repair inconsistent aggregator imports/helpers in the remote merge. Final fault
  confidence remains estimator confidence; newer local decision helpers remain
  available, and the new claim-risk/route analyzers are retained.
- Fill all required photo-prompt placeholders.
- Use Optional annotations so login dependencies import under the existing Python 3.9 environment.
- Expose unavailable claim-risk model dependencies through the existing logged rule fallback.

## Validation

Frontend production build passes. Two new branch-integration tests pass: operational
endpoints require login, and customer roles cannot access Ops/Admin endpoints.
The full inherited suite currently reports 15 tests, 2 failures and 3 errors:
old assertions expect public EXTERNAL rather than NEITHER and exactly two global
joblib loads; three persistence tests do not isolate the workflow DB access and
attempt network calls. These are not claimed as passing end-to-end validation.
The local environment lacks XGBoost, which the new claim-risk artifact requires;
its pinned dependency is already in backend/requirements.txt. Install using a
supported Python environment before validating that model's predictions.
