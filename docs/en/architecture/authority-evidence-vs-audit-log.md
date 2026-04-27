# Authority Evidence vs Audit Log

## Why this distinction exists

In regulated-action governance, recording events is not sufficient for bind-time admissibility decisions. VERITAS distinguishes between audit history and bind-time authority proof.

## Audit log: record of what happened

An audit log (for example, TrustLog-oriented operational lineage) records **what occurred**:

- decision and bind events
- timestamps and actors
- outcome transitions
- processing lineage

This is useful for traceability and post-incident analysis.

## Authority evidence: proof of why action was admissible

Authority evidence records **why an action was authorized/admissible at bind time**, including:

- which action-class contract applied
- actor role and authority source references
- scope grants and scope limitations
- validity window and verification result
- deterministic evidence hash for integrity checks

This is required for runtime authority validation and commit-boundary adjudication.

## Non-substitutability rule

Audit logs and authority evidence are complementary, not interchangeable:

- Audit log alone must **not** authorize commit.
- Commit permission is determined by bind-time validation of authority evidence + action contract + predicates.
- If authority evidence is missing/expired/invalid/indeterminate, path remains fail-closed.

## Validation and integrity requirements

Authority evidence must be validated and integrity-protected:

- verification result is checked (`valid`, `invalid`, `expired`, `missing`, `stale`, `indeterminate`)
- validity window is evaluated at bind time
- evidence should carry deterministic hash (`evidence_hash`)
- policy snapshot and actor identity requirements are evaluated by runtime predicates

## Fail-closed outcomes

When authority state is insufficiently admissible:

- `missing` -> block
- `expired` -> block
- `invalid` -> block
- `indeterminate` -> refuse

This ensures bind-time action authorization cannot be inferred from event recording alone.

## What is not claimed

This distinction is an implementation design for reviewable regulated action governance. It is not a claim of legal compliance, regulatory approval, or third-party certification.
