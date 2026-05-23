# RSA ↔ VERITAS Local V.I.K.I. Mock Receiver E2E Harness Validation Snapshot

## 1. Purpose

This snapshot documents the current validation state of the fixture-driven local V.I.K.I. mock receiver E2E harness.

- This is documentation-only.
- This is not a new runtime implementation.
- This is not a live V.I.K.I. integration.
- This is not a production API endpoint.
- This records the implemented local fixture-driven E2E harness behavior after it was merged.

## 2. Implemented harness surface

Harness test file:

- `tests/governance/test_local_viki_mock_receiver_e2e_harness.py`

Fixture directory:

- `tests/fixtures/local_viki_mock_receiver/`

The harness:

- reads static synthetic JSON fixture files as raw text
- passes raw fixture text into `ingest_local_viki_mock_payload()`
- uses a fixed receiver clock
- enables the explicit test-only guard with `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE=1`
- asserts expected VERITAS decisions
- asserts default audit redaction
- asserts fail-closed behavior for invalid fixtures
- asserts the guard raises `RuntimeError` when disabled

The harness does not:

- open a socket
- run an HTTP server
- call a network service
- connect to live V.I.K.I.
- consume live LLM text
- process real KYC data
- add production commit authority

## 3. E2E validation flow

```text
static synthetic JSON fixture
→ raw fixture text
→ ingest_local_viki_mock_payload()
→ RSASandboxPayload
→ evaluate_rsa_sandbox_signal()
→ VERITAS decision
→ redacted audit output
```

This validates the local mock path without introducing network transport or live middleware.

## 4. Positive fixture inventory

| Fixture file | rsa_status | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Validation result |
| --- | --- | --- | --- | --- | --- |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_001_safe_proceed.json` | SAFE_PROCEED | CONTINUE_TO_BIND_BOUNDARY | UPSTREAM_SAFE_PROCEED_SIGNAL | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_002_density_throttled.json` | DENSITY_THROTTLED | CONTINUE_WITH_UPSTREAM_INTERVENTION_LOGGED | UPSTREAM_INTERVENTION_DENSITY_THROTTLE | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_003_algorithmic_humility_engaged.json` | ALGORITHMIC_HUMILITY_ENGAGED | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_INCOMPLETE_KYC_CONTEXT | SUSPENDED_NOT_COMMITTED | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_pos_004_deferral_engaged.json` | DEFERRAL_ENGAGED | BLOCK_FINAL_COMMIT | UPSTREAM_CRITICAL_DEFERRAL_SIGNAL | BLOCKED_NOT_COMMITTED | Implemented |

## 5. Negative fixture inventory

Negative fixtures validate that malformed, missing, unknown, invalid, or wrongly shaped payloads are never converted into `SAFE_PROCEED`.

| Fixture file | Invalid condition | Expected continuation_decision | Expected reason_code | Expected sandbox_commit_state | Expected next action | Validation result |
| --- | --- | --- | --- | --- | --- | --- |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_001_invalid_json.json` | Malformed JSON | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_002_missing_rsa_status.json` | Missing rsa_status | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_003_unknown_rsa_status.json` | Unknown rsa_status | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_004_invalid_timestamp.json` | Invalid timestamp | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_005_payload_shape_array.json` | Payload shape is array instead of object | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_006_missing_trigger_source.json` | Missing trigger_source | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |
| `tests/fixtures/local_viki_mock_receiver/viki_neg_007_null_required_field.json` | rsa_status present but null | PAUSE_FOR_HUMAN_REVIEW | UPSTREAM_MOCK_PAYLOAD_INVALID | SUSPENDED_NOT_COMMITTED | REQUEST_VALID_SYNTHETIC_PAYLOAD_OR_HUMAN_REVIEW | Implemented |

## 6. Guard validation

The E2E harness includes a guard-path test.

Expected behavior:

- when `VERITAS_LOCAL_VIKI_MOCK_RECEIVER_ENABLE` is unset, `ingest_local_viki_mock_payload()` raises `RuntimeError`
- the guard blocks before payload processing
- this prevents accidental use outside explicit local mock test contexts

Clarifications:

- the guard is a test-only opt-in control
- the guard is not production authentication
- the guard does not make this receiver production-ready

## 7. Audit redaction validation

Every positive E2E fixture asserts:

- `audit_entry.upstream_signal_source == "RSA"`
- `audit_entry.original_llm_intent == "[REDACTED]"`
- `audit_entry.rsa_action_taken == "[REDACTED]"`
- `audit_entry.veritas_continuation_decision` matches the expected `continuation_decision`
- `audit_entry.veritas_sandbox_commit_state` matches the expected `sandbox_commit_state`

For negative fixtures, the harness asserts:

- `audit_entry.rsa_status == "INVALID_OR_UNAVAILABLE"`
- `audit_entry.trigger_source == "LOCAL_VIKI_MOCK_RECEIVER"`
- `audit_entry.original_llm_intent == "[REDACTED]"`
- `audit_entry.rsa_action_taken == "[REDACTED]"`

This means:

- raw upstream reasoning is not stored
- V.I.K.I. internal reasoning is not stored
- chain-of-thought is not stored
- hidden model state is not stored

## 8. No-network validation boundary

- The harness reads only local fixture files.
- The harness does not mock `requests` or `httpx`.
- The harness does not require sockets.
- The harness does not perform network I/O.
- The harness does not use live middleware.
- The harness does not use secrets or credentials.

## 9. Test command

Intended focused test command:

```bash
python -m pytest -q tests/governance/test_local_viki_mock_receiver.py tests/governance/test_local_viki_mock_receiver_e2e_harness.py
```

If applicable:

```bash
python -m pytest -q tests/governance/test_rsa_sandbox_receiver.py
```

This snapshot does not modify tests or CI; it only records the intended validation surface.

## 10. Compatibility validation

The E2E harness preserves:

- `rsa_status`
- `RSASandboxPayload`
- `evaluate_rsa_sandbox_signal()`
- `upstream_signal_source = "RSA"`

Compatibility clarifications:

- `rsa_status` was not renamed to `viki_status`
- `RSASandboxPayload` was not renamed to `VIKIPayload`
- `evaluate_rsa_sandbox_signal()` remains the downstream evaluator
- naming migration remains out of scope and must be handled as a separate v2 migration

## 11. What this snapshot validates

- Static synthetic JSON fixtures exist.
- The harness drives the receiver from raw fixture text.
- The four positive `rsa_status` variants map to expected VERITAS decisions.
- Negative fixtures fail closed.
- Malformed JSON does not proceed.
- Unknown `rsa_status` does not proceed.
- Invalid timestamp does not proceed.
- Array payload shape does not proceed.
- Missing trigger_source does not proceed.
- A present-but-null required field does not proceed.
- Default audit redaction remains active.
- The explicit guard is validated.
- No live V.I.K.I. connection exists.

## 12. What this snapshot does not validate

- It does not validate live V.I.K.I. middleware.
- It does not validate network transport.
- It does not validate authentication or authorization.
- It does not validate production AML/KYC compliance.
- It does not validate regulatory approval.
- It does not provide legal advice.
- It does not validate real KYC data.
- It does not validate live LLM text.
- It does not make the local mock receiver production-ready.
- It does not replace the need for controlled integration threat modeling.

## 13. Recommended next PR after this snapshot

The next safe PR should be one of:

- controlled live V.I.K.I. integration threat model
- live payload schema draft
- local mock receiver CI validation command documentation
- fixture manifest / coverage index

Recommended:

The safest next PR is the controlled live V.I.K.I. integration threat model, because the local mock phase now has design notes, fixture plan, implementation, validation snapshot, and fixture-driven E2E harness.


## Related pre-live artifact

- [Controlled live V.I.K.I. integration threat model (documentation-only pre-live gate)](./rsa-veritas-controlled-live-viki-integration-threat-model.md)
