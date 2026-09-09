# Decision-to-Effect E2E — Historical Stop Record

## Status

The stop condition documented here originated at merge commit
`e039496cefad9793f342f261940e4009806e5859` (PR #2142 era).

It is **superseded for the controlled CI proof scope**.

The repository now has later native-v2 sandbox primitives for certificate-
validated HTTPS dispatch, independent read-only reconciliation, durable
reconciliation evidence, atomic BindReceipt / Outcome publication, replacement
business-event blocking, crash recovery, and controlled real-TLS /
real-PostgreSQL composition.

TASK-007 adds a dedicated workflow:

`.github/workflows/reproducible-decision-to-effect-e2e.yml`

That workflow must generate a passing, source-SHA-bound:

- `report.json`; and
- `evidence.json`

under the runtime artifact path `artifacts/real-decision-to-effect-e2e/` and
upload them as the `reproducible-decision-to-effect-e2e` GitHub Actions
artifact.

## What resolved this stop for the controlled scope

The controlled proof no longer relies on the old runner-local reconciliation
shortcut described below. It uses the current sandbox execution/reconciliation
path and requires the full proof conjunction to pass:

1. current `/v1/decide` route exercised with controlled model output;
2. CanonicalDecisionArtifact independently verified;
3. selected sandbox action and deterministic promotion verified;
4. native v2 authorization verified against that exact promoted intent;
5. single-use authorization consumed in real PostgreSQL;
6. current governance rechecks exercised;
7. one certificate-validated TLS POST reaches the pinned sandbox endpoint;
8. the synthetic event is durably persisted in a dedicated PostgreSQL database;
9. independent read-only reconciliation confirms the persisted operation;
10. reconciliation evidence is archived;
11. BindReceipt and Outcome link back to the original decision and intent;
12. a lost-response + lookup-outage fault preserves `EFFECT_UNKNOWN`;
13. no blind redispatch occurs; and
14. repeat recovery does not perform another POST or reconciliation lookup.

The workflow fails unless every controlled proof conjunction is true.

## Scope boundary

This resolution is intentionally narrower than production validation.

A passing controlled proof does **not** establish:

- production readiness;
- real customer credentials;
- a real customer endpoint;
- independent production infrastructure ownership;
- external UTC clock trust;
- TrustLog exactly-once publication;
- regulatory approval or certification.

Therefore this file must not be interpreted as a production-readiness marker.

## Historical context

The original stop report stated that the then-current proof path could not
independently authenticate external effect evidence strongly enough to support a
Decision-to-Effect claim. That warning was correct for that historical commit.
It is retained here as provenance, but current status must be determined from
the current source SHA and the dedicated Decision-to-Effect workflow result.
