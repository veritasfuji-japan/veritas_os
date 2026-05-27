# Authority Evidence Ingestion (v1)

`veritas_os.governance.authority_evidence_ingestion` provides a **local/offline deterministic ingestion adapter** that normalizes external or mock authority payloads into VERITAS OS `AuthorityEvidence` artifacts.

## Scope

- Local normalization only (no network calls, no credentials, no SaaS dependencies).
- Deterministic transformation for bind-time admissibility flows.
- Compatibility with existing fail-closed runtime governance and commit-boundary validation.

## What it does

- Accepts plain dictionary payloads.
- Maps supported external aliases (for example `evidence_id`, `subject`, `expires_at`).
- Produces a normalized `AuthorityEvidence` dataclass.
- Defaults unknown verification states to `indeterminate`.
- Preserves source facts under `metadata`.
- Computes `evidence_hash` via deterministic canonical digest.

## Safety model

- Structurally invalid payloads raise `ValueError` and fail closed.
- Missing/invalid/expired/indeterminate evidence remains blocked by existing runtime authority checks.

## Non-goals

This adapter is **not**:

- legal advice,
- regulatory approval,
- third-party certification,
- or a live production integration endpoint.
