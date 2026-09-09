# Large Consolidation Audit — Phase 2 Dependency & Consumer Matrices

Status: **PHASE 2 / NON-DESTRUCTIVE**  
Audited product main: `52752dbf766d9994f2f3267af47e904748d347a6`  
Frozen controlled E2E anchor: `ada46f2fe324dd3cbcff6be59d56c4f75c4a6bdc`  
Phase 1: PR #2217

Machine-readable baseline:
`artifacts/consolidation-audit/2026-09-10-phase2-baseline.json`

Generator:
`scripts/audit_large_consolidation_phase2.py`

Generated runtime artifact:
`artifacts/consolidation-audit/phase2-generated.json`

## 1. Purpose

Phase 1 identified candidate clusters. Phase 2 asks a stricter question:

> Which code is actually protected, actively consumed, duplicated, compatibility-only, or unsupported?

This phase still performs **no runtime deletion**. It turns candidate families into dependency and consumer evidence so the first actual consolidation PR can be narrow and defensible.

## 2. Frozen-core dependency closure

The Architecture Freeze manifest lists the explicit controlled Decision-to-Effect proof files. Phase 2 now computes two static Python closures:

- **runtime closure** — starts only from frozen runtime policy modules;
- **proof closure** — also includes the dedicated controlled E2E proof test.

The generator follows in-repository Python imports transitively and records inbound importers for every module in the protected closure.

Anything in the generated runtime closure is treated as `FROZEN_CORE` for consolidation purposes unless a later, narrower proof establishes that a dependency can be replaced without changing frozen semantics.

### Limitation

This is static Python import evidence. It does not prove reachability through:

- dynamic imports;
- plugin discovery;
- reflection;
- configuration-driven module names; or
- external package consumers.

Therefore absence from the static closure is **not automatically a deletion authorization**.

## 3. Legacy policy SHA-256 verifier

Candidate:

`veritas_os/policy/signing.py::verify_manifest_sha256`

### Evidence

The function itself labels the path as legacy SHA-256 verification.

Exact repository search found:

- the definition;
- direct unit tests; and
- historical/review documentation.

The initial repository-wide search found **no supported runtime, CLI, script or workflow caller outside the defining module**.

Phase 2 therefore upgrades this from `COMPATIBILITY_CANDIDATE` to:

**`DEAD_CANDIDATE / HIGH confidence`**

but still sets:

**`deletion_permitted=false`**

The Phase 2 generator repeats exact consumer scanning on the PR source. If a supported runtime/script/workflow consumer appears, the classification automatically falls back to `COMPATIBILITY_CANDIDATE`.

This is the current best candidate for the **first narrow post-audit cleanup PR**.

## 4. TrustLog verifier role matrix

The initial “duplicate verifier” concern is now materially narrowed.

### `veritas_os/logging/trust_log.py::verify_trust_log`

Role:

**full encrypted TrustLog compatibility verifier**

It delegates full-ledger verification and preserves historical compatibility fields such as `broken_reason`.

Evidence shows active runtime/test consumers.

Classification:

**`ACTIVE_NON_CORE`**

### `veritas_os/audit/trustlog_verify.py::verify_trustlogs`

Role:

**stable combined full + witness ledger verifier**

It is the unified verifier used by CLI/script/test paths and handles full ledger, signed witness ledger, linkage and structured error semantics.

Classification:

**`ACTIVE_NON_CORE`**

### `veritas_os/scripts/verify_trust_log.py::verify_entries`

Role:

**backward-compatible tuple-output helper**

The script's actual CLI `main()` uses `verify_trustlogs`, not `verify_entries`.

The helper's own docstring says it is retained for existing tests/tools.

Classification:

**`COMPATIBILITY_CANDIDATE`**

### `compute_hash`

Same script, same pattern: explicitly retained for backward-compatible tests/tools.

Classification:

**`COMPATIBILITY_CANDIDATE`**

### Conclusion

Do **not** merge or delete the active TrustLog verifiers based on naming similarity. The safe cleanup target, if any, is the compatibility-helper surface, and only after external/tool import expectations are checked.

## 5. plan8–plan17 test overlap matrix

Phase 2 inspected the ten sequential coverage-plan suites and records exact test names and target-module reference counts.

High-confidence overlaps include:

### Replay query-parameter failure default

Three tests cover the same safety outcome:

- `test_replay_decision_endpoint_query_params_error_defaults_true`
- `test_replay_decision_endpoint_defaults_mock_true_on_query_error`
- `test_routes_replay_decision_query_param_error_defaults_to_mock_true`

All assert that a query parsing failure defaults to `mock_external_apis=True`.

Classification:

**`DUPLICATE_CANDIDATE / HIGH`**

### Unknown rollout strategy

Two tests cover safe-full fallback:

- `test_rollout_enforcement_unknown_strategy_defaults_to_safe_full`
- `test_pipeline_rollout_unknown_strategy_falls_back_to_safe_full`

Classification:

**`DUPLICATE_CANDIDATE / HIGH`**

### Pipeline unavailable / lazy-state reset

Two related tests cover the unavailable-pipeline reset path.

Classification:

**`DUPLICATE_CANDIDATE / MEDIUM`**

### Nonce cleanup scheduler exception handling

Several tests cover neighboring scheduler failure/reschedule/stop behavior.

Classification:

**`DUPLICATE_CANDIDATE / MEDIUM`**

These require case-by-case consolidation because some assert distinct lifecycle states.

### Effective nonce maximum tests

The plan files also contain tests for:

- import failure fallback;
- non-integer server override fallback; and
- valid integer override.

These are related but test **different branches**, so they are classified:

**`ACTIVE_NON_CORE`**

The audit explicitly rejects “same function target = duplicate test” as a cleanup rule.

## 6. Parallel dry-run family matrix

There are two structurally parallel policy families.

### Canonical promotion family

`canonical_promotion_live_adapter_dry_run_*`

### Live-adapter family

`live_adapter_dry_run_*`

Phase 2 finds **11 matching suffix pairs**:

- authority_evidence_linkage
- bind_authorization_gate_review
- bind_pre_dispatch_review
- credential_authorization
- dispatch_readiness
- endpoint_allowlist
- final_bind_authorization_readiness
- human_approval_linkage
- operator_dispatch_review
- readiness
- request

Canonical-promotion-only responsibilities:

- bind_context_hash_derivation
- final_credential_scope_recheck
- final_endpoint_identity_recheck
- fresh_verified_source_gate
- runtime_risk_review

Live-only responsibility:

- human_approval_requirement_satisfaction

### Conclusion

This is strong evidence of **structural parallelism**, not behavioral duplication.

The frozen native-v2 authorization/recheck path imports this lineage. Therefore the entire family remains:

**`UNCERTAIN / deletion_permitted=false`**

No dry-run consolidation should begin before a symbol-level responsibility comparison is tied back to the generated frozen dependency closure.

## 7. Ranked first consolidation candidates

Current ranking:

| Rank | Target | Classification | Blast radius |
| ---: | --- | --- | --- |
| 1 | `verify_manifest_sha256` | DEAD_CANDIDATE | LOW |
| 2 | exact plan8–plan17 duplicate tests | DUPLICATE_CANDIDATE | LOW |
| 3 | `verify_entries` / `compute_hash` compatibility helpers | COMPATIBILITY_CANDIDATE | LOW–MEDIUM |
| 4 | dry-run packet families | UNCERTAIN | HIGH |
| 5 | TrustLog verifier architecture | ACTIVE_NON_CORE | HIGH |

This ranking is intentionally conservative.

## 8. What Phase 2 does not authorize

Phase 2 does **not** authorize:

- deletion of `verify_manifest_sha256`;
- deleting test files wholesale;
- TrustLog verifier unification;
- dry-run family collapse;
- API schema restructuring;
- migration changes;
- frozen-proof semantic changes.

The first actual deletion/refactor PR is a **separate Human CEO review point**.

## 9. Exit condition

Phase 2 is complete when the dedicated generator and CI artifact establish:

- frozen runtime/proof dependency closures;
- current exact consumer references;
- TrustLog role evidence;
- plan-test overlap evidence;
- legacy verifier consumer evidence;
- dry-run structural pairing; and
- a ranked first cleanup target.

If the generated evidence remains consistent with this baseline, the next recommended action is a narrow PR for the lowest-blast-radius confirmed candidate, not a repository-wide cleanup.
