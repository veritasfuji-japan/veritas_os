# Bind Coverage Evidence Artifact

## Scope
This artifact summarizes FastAPI runtime route classification against the canonical bind coverage registry.

## Summary table
| Metric | Value |
| --- | --- |
| total_runtime_routes | 47 |
| total_effect_bearing_routes | 17 |
| bind_governed_routes | 5 |
| audited_exemptions | 12 |
| unclassified_routes | 0 |
| status | ok |

## Bind-governed routes
- `PUT /v1/compliance/config` (bind_target_metadata_present=True)
- `PUT /v1/governance/policy` (bind_target_metadata_present=True)
- `POST /v1/governance/policy-bundles/promote` (bind_target_metadata_present=True)
- `POST /v1/system/halt` (bind_target_metadata_present=True)
- `POST /v1/system/resume` (bind_target_metadata_present=True)

## Audited exemptions
- `POST /v1/decide` reason=Decision recording is reviewable output and not an execution permission path.; risk_level=medium; governance_owner=governance; review_required_by=quarterly
- `POST /v1/decision/replay/{decision_id}` reason=Legacy replay alias is audit-only and has no external execution side effects.; risk_level=low; governance_owner=audit; review_required_by=quarterly
- `POST /v1/fuji/validate` reason=Validation endpoint evaluates gate status but does not commit execution.; risk_level=medium; governance_owner=governance; review_required_by=quarterly
- `POST /v1/memory/erase` reason=Memory erasure affects local memory store but is not a bind target catalog operation.; risk_level=high; governance_owner=memory; review_required_by=monthly
- `POST /v1/memory/get` reason=Lookup endpoint uses POST for typed request body; retrieval only.; risk_level=low; governance_owner=memory; review_required_by=quarterly
- `POST /v1/memory/put` reason=Memory write persists internal context only; no governed external execution target.; risk_level=medium; governance_owner=memory; review_required_by=quarterly
- `POST /v1/memory/search` reason=Search uses POST for payload size/shape but is read semantics only.; risk_level=low; governance_owner=memory; review_required_by=quarterly
- `POST /v1/replay/{decision_id}` reason=Replay endpoint reproduces prior decisions for audit and does not authorize execution.; risk_level=low; governance_owner=audit; review_required_by=quarterly
- `POST /v1/trust/feedback` reason=Trust feedback updates scoring telemetry only; no execution authorization.; risk_level=low; governance_owner=trust; review_required_by=quarterly
- `POST /v1/wat/issue-shadow` reason=Shadow WAT issuance is observer-lane telemetry and non-enforcement.; risk_level=medium; governance_owner=governance; review_required_by=quarterly
- `POST /v1/wat/revocation/{wat_id}` reason=Revocation mutates WAT lane state but is not a bind-governed execution path.; risk_level=high; governance_owner=governance; review_required_by=monthly
- `POST /v1/wat/validate-shadow` reason=Shadow validation checks signatures without granting execution privileges.; risk_level=medium; governance_owner=governance; review_required_by=quarterly

## Unclassified routes
- None

## Catalog / registry consistency
- No mismatch detected between bind target catalog and bind-governed registry targets.

## Registry validation errors
- None

## Interpretation boundaries
- This artifact proves route classification coverage, not external legal certification.
- This artifact does not prove every business action is safe.
- Bind-governed routes are the routes currently wired to the Bind target catalog.
- Audited exemptions require periodic governance review.

## How to regenerate
```bash
python scripts/governance/export_bind_coverage_evidence.py
```
