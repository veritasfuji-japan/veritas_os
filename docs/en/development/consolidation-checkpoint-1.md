# Lightweight Consolidation Checkpoint 1

Baseline: `236a468cc426f57e70f9aad84eee1c09e9f2b5f9` (PR #2195 merged).
Date: 2026-09-07. This is a bounded static inventory, not a whole-repository
dead-code proof, security audit, or production certification.

## Classification and disposition

| Label | Meaning and action |
| --- | --- |
| KEEP | Used behavior or an independent trust boundary; retain. |
| PUBLIC_COMPAT | Public import/version compatibility; retain pending consumer migration. |
| TEST_ONLY | Test infrastructure; changes require collection and assertion checks. |
| REMOVE_NEXT_MAJOR | Proposed future removal after compatibility review, not permission to delete now. |
| DEAD | Requires reference, dynamic import, public API, operational and recovery-path review. No runtime item is assigned this label here. |

## Safe fixes in this checkpoint

Three direct module-level test names were defined twice. Python replaced the
earlier definitions before pytest collection. The tests are not equivalent.

| File under `veritas_os/tests/` | Earlier definition now collected |
| --- | --- |
| `unit/test_kernel_decide_ext.py` | `test_decide_simple_qa_time_response_contract` |
| `integration/test_decide_e2e_ext.py` | `test_run_decide_pipeline_happy_path_with_trust_receipt` |
| `integration/test_decide_e2e_ext.py` | `test_run_decide_pipeline_explicit_options_preserve_ids_without_ml_gate` |

All original assertions remain. The newly restored explicit-options test now
uses `monkeypatch.setitem` for its kernel module stub, so teardown restores the
previous module. Existing later definitions retain their original names.
These changes are TEST_ONLY; no production authorization or verifier changes.

`tests/test_unique_test_names.py` prevents direct module/class test-definition
overwrites in tracked pytest files. It parses ASTs without importing the tests.
It does not detect conditional definitions, dynamic assignments, imported-name
collisions, or every possible pytest customization.

Validation: the two affected files pass 194 tests; with the detector tests,
197 tests pass. Full CI is a separate gate and is not claimed by these counts.

## Similar tests and helpers: inventory, not deletion

The baseline has 566 tracked Python files under `tests` directories. Comparing
module-level test ASTs (including names, decorators and docstrings, excluding
source positions) identifies 15 identical groups / 38 definitions across files.
For example, schema-existence tests in `tests/demo/test_*_schema.py` have identical
bodies but refer to different module-level schema paths. Keep those guarantees;
textual equality is not evidence that their coverage is redundant.

Module-level helper definitions in tracked non-test Python files:

| Name | Definitions | Disposition |
| --- | ---: | --- |
| `_digest` | 50 | KEEP; five exact AST groups contain 18, 5, 12, 2 and 4 definitions, but global bindings still differ. |
| `_timestamp` | 18 | KEEP; compare parsing and error contracts before sharing. |
| `_json` | 20 | KEEP; accepted values and normalization can differ. |
| `_fail` | 16 | KEEP; domain-specific failure types/codes must remain explicit. |

For example, `policy/live_adapter_bind_authorization_codec.py` accepts a digest
domain argument, while `policy/human_approval_requirement_resolution.py` uses its
own DOMAIN. Their JSON value acceptance and timestamp error contracts differ.
No verifier or helper is merged merely because its name or AST looks alike.

## Legacy shim inventory

39 non-test files match the narrow `_TARGET_MODULE` plus `import_module`/`sys`
alias pattern. Paths below are relative to `veritas_os/core/`. All are
PUBLIC_COMPAT today; other compatibility mechanisms are outside this heuristic.

| Group | Module stems |
| --- | --- |
| FUJI (6) | `fuji_codes`, `fuji_helpers`, `fuji_injection`, `fuji_policy`, `fuji_policy_rollout`, `fuji_safety_head` |
| Memory (14) | `memory_compliance`, `memory_distillation`, `memory_evidence`, `memory_helpers`, `memory_lifecycle`, `memory_search_helpers`, `memory_security`, `memory_storage`, `memory_store`, `memory_store_compat`, `memory_store_helpers`, `memory_summary_helpers`, `memory_vector`, `models/memory_model` |
| Pipeline (19) | `pipeline_compat`, `pipeline_contracts`, `pipeline_critique`, `pipeline_decide_stages`, `pipeline_evidence`, `pipeline_execute`, `pipeline_gate`, `pipeline_helpers`, `pipeline_inputs`, `pipeline_memory_adapter`, `pipeline_persist`, `pipeline_persistence`, `pipeline_policy`, `pipeline_replay`, `pipeline_response`, `pipeline_retrieval`, `pipeline_signature_adapter`, `pipeline_types`, `pipeline_web_adapter` |

`core/_shim_deprecation.py` mentions v2.2.0 and a not-before date of 2026-08-01.
That date passing does not prove migration. `test_memory_vector_core.py` and
`test_legacy_core_shim_deprecations.py` still exercise old imports and alias
behavior. A REMOVE_NEXT_MAJOR proposal needs an explicit release decision and
external-consumer review; nothing is deleted here.

## Builder candidates

An AST name/attribute/import scan finds 61 `build_*` definitions whose references
outside their defining file occur only in tests. This is not a TEST_ONLY or DEAD
classification: same-file callers, CLI entrypoints and public consumers matter.
Examples rejected as deletion candidates:

| Builder | Evidence | Label |
| --- | --- | --- |
| `audit/anchor_backends.py:build_timestamp_request` | Same-file timestamp request caller | KEEP |
| `audit/trustlog_signed.py:build_trustlog_summary` | Same-file signed audit caller | KEEP |
| `sdk/python/examples/aml_kyc_webhook_bind.py:build_review_payload` | Same-file example flow callers | KEEP |

The remaining candidates need manual reference review. Token searches alone did
not establish a runtime builder with no uses. Dynamic/external uses are not
resolved by either heuristic.

## Largest schema candidates

Top five tracked `*schema.json` files by physical lines; size is a review signal,
not evidence that fields or embedded definitions are unnecessary.

| File under `schemas/` | Lines | UTF-8 bytes |
| --- | ---: | ---: |
| `adapter-dry-run-fixture-result-v1.schema.json` | 6582 | 185226 |
| `adapter-dry-run-plan-v1.schema.json` | 4475 | 122180 |
| `bind-adapter-contract-selection-v1.schema.json` | 3995 | 106900 |
| `canonical-bind-preflight-adjudication-v1.schema.json` | 3087 | 81710 |
| `live-adapter-dry-run-request-v1.schema.json` | 2878 | 85831 |

KEEP until schema generation, reference resolution, version compatibility and
hash/signature effects have been reviewed. No schema changes in this checkpoint.

## Next boundary

Complete this test-only correction and review the inventory before native v2
execution. For one selected integration, define trust anchors, clock behavior,
material-change rules and ambiguous-outcome handling before external effects.
Freeze after the first complete path passes both normal and failure/recovery
scenarios; then perform the larger consolidation audit. One unused E2E path is
not proof of dead code. No obsolete PRs or branches are closed/deleted here.
