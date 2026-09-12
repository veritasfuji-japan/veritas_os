# VERITAS / CAGE Phase 3 — Deterministic Fixture Proof

## Status

Implementation scope for the source-reviewed Phase 3 synthetic proof.

This proof is:

- synthetic;
- deterministic;
- side-effect-free;
- based on the existing seven VERITAS AML/KYC regulated-action fixtures;
- projected into the source-confirmed CAGE Provider03 contract.

It is **not** a live CAGE runtime integration, production deployment, commercial integration, Google product adoption, or endorsement.

## Source baselines

VERITAS proof branch starts from:

- `veritas_os/main` at `718de19c8e6f0f783d3b49feaa6577742ef35b54`

CAGE contract reference observed for this implementation:

- repository: `google/cybernetic-agent-governance-engine`
- source commit: `ecbcce3253cb55c333f47009c40a45dbc5b3a454`
- Provider03 path: `src/integrations/provider_03/provider.py`

The current CAGE Provider03 source exposes:

- `fetch_baseline(region)`
- `validate_fria(payload)`
- `submit_evidence(thread_id, evidence_hash)`
- Provider03-specific `ingest_bind_receipt(receipt)`

Provider03 verdict semantics used here:

- `APPROVED` -> admitted
- `ESCALATE` -> denied for execution plus `needs_human_review=true`
- `REJECTED` -> hard deny
- missing/unknown verdict -> fail closed

## Important action-context compatibility detail

Current CAGE source applies field mapping only when the caller supplies
`action_context_field_map`.

The Phase 3 proof therefore fixes the explicit map:

```text
amount -> magnitude
symbol -> context
```

The proof does not claim that these aliases are automatically applied by CAGE
without configuration.

The normalization is non-mutating with respect to the caller payload.

## Existing VERITAS fixture

The proof does not rewrite the existing fixture semantics.

Fixture:

`veritas_os/sample_data/governance/aml_kyc_regulated_action_path/scenarios.json`

Expected outcomes remain:

| Scenario | VERITAS | Provider03 | CAGE projection |
|---|---|---|---|
| allowed internal escalation | `commit` | `APPROVED` | admitted |
| prohibited account freeze | `block` | `REJECTED` | denied |
| prohibited customer notification | `block` | `REJECTED` | denied |
| stale sanctions screening | `escalate` | `ESCALATE` | human review / DEFER |
| missing authority | `block` | `REJECTED` | denied |
| high irreversibility without approval | `block` | `REJECTED` | denied |
| policy uncertainty | `block` | `REJECTED` | denied |

Expected verdict distribution:

```text
APPROVED = 1
ESCALATE = 1
REJECTED = 5
```

## Hash-domain separation

Phase 3 intentionally keeps two receipt hashes distinct.

### VERITAS bind-receipt content hash

`veritas_bind_receipt_hash`

This recreates the existing VERITAS regulated-action receipt hash over the
receipt body before `bind_receipt_hash` is inserted.

### CAGE Provider03 ingest digest

`cage_ingested_bind_receipt_digest`

This models current Provider03 `ingest_bind_receipt(receipt)` semantics:

```text
complete receipt
-> RFC 8785 JCS
-> SHA-256 hex digest
```

The proof does not assume these two hashes are equal.

The exact input domain for each value is recorded in every scenario artifact.

## Bounded JCS implementation

The proof uses a bounded RFC 8785-compatible canonicalization function for the
fixture artifact domain.

Supported JSON values:

- string;
- integer;
- boolean;
- null;
- list;
- string-keyed object.

Floating-point values are rejected rather than approximated. This prevents
cross-language number-format drift from being hidden inside the fixture proof.

This bounded helper is not presented as a general-purpose replacement for the
full CAGE JCS implementation.

## TrustLog boundary

The existing regulated-action fixture emits a `trustlog_lineage_ref`.

Phase 3 records:

```text
trustlog_proof_status = lineage_only
```

and:

```text
witness_hash = null
```

unless a separate real TrustLog witness-generation path is actually executed.

The proof never upgrades a lineage reference into a fabricated witness claim.

## Reviewer artifacts

Run:

```bash
python scripts/run_veritas_cage_phase3_fixture.py \
  --output-dir artifacts/veritas-cage-phase3
```

The runner produces:

- `manifest.json`
- seven per-scenario JSON artifacts
- `replay_report.json`
- `negative_test_report.json`
- `summary.json`

The dedicated GitHub Actions workflow adds:

- `run-manifest.json`
- source commit identity
- SHA-256 identities for generated JSON artifacts
- GitHub Actions run identity

## Deterministic replay

The proof builds the complete bundle twice.

For every scenario it compares:

- VERITAS outcome;
- Provider03 verdict;
- VERITAS bind receipt hash;
- CAGE receipt ingest digest;
- evidence seal hash.

All deterministic comparisons must match.

## Negative proof checks

The proof explicitly verifies:

- unknown verdict fails closed;
- missing verdict fails closed;
- synthetic endpoint failure fails closed with `ENDPOINT_ERROR`;
- explicit action-context mapping is correct;
- normalization does not mutate caller input;
- bind-receipt mutation changes the CAGE ingest digest;
- evidence mutation changes the seal hash;
- missing authority remains rejected;
- missing required human approval remains rejected;
- stale evidence remains `ESCALATE` / human review rather than `APPROVED`.

## Evidence seal

Each scenario builds a deterministic synthetic evidence artifact containing:

- fixture identity;
- deterministic thread ID;
- VERITAS outcome;
- Provider03 verdict;
- projected CAGE admission state;
- bind receipt identity;
- both receipt hash domains;
- authority evidence identity;
- TrustLog lineage state.

The evidence artifact is canonicalized with the bounded JCS helper and hashed
with SHA-256 to produce the Phase 3 `seal_hash`.

This is a deterministic interoperability proof artifact, not evidence of a
live external CAGE endpoint having received or signed the payload.

## CI

Workflow:

`.github/workflows/veritas-cage-phase3.yml`

The workflow:

1. runs focused Phase 3 tests;
2. executes the seven-scenario proof;
3. performs deterministic replay;
4. performs negative/tamper checks;
5. binds artifacts to the checked-out VERITAS source SHA;
6. uploads a 90-day reviewer artifact.

## Exit criteria

Phase 3 is complete only when:

- all seven existing fixtures preserve their expected outcomes;
- verdict distribution remains `1 / 1 / 5`;
- `ESCALATE` includes the human-review marker;
- fail-closed negative checks pass;
- bind receipt and evidence mutation checks pass;
- two independent proof runs replay identically;
- the dedicated source-bound workflow is green;
- reviewer-facing artifacts are preserved.

Only after that should the work move to Lars review and the next explicit
interoperability gate.

## Non-claims

This proof does not establish:

- live CAGE runtime integration;
- production readiness;
- real customer credentials or endpoints;
- real banking effects;
- production AML/KYC compliance;
- regulatory approval or certification;
- Google product adoption;
- Google endorsement;
- commercial integration.
