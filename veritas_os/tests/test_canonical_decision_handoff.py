"""Runtime and adversarial tests for CanonicalDecisionHandoff v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from veritas_os.policy.canonical_decision_handoff import (
    ASSERTION_VALUE_DIGEST_PROFILE,
    CandidateHashBindingAssertion,
    CanonicalDecisionHandoffReasonCode,
    CanonicalDecisionHandoffStatus,
    CanonicalDecisionHandoffValidationContext,
    TrustedValueAssertion,
    canonical_handoff_assertion_value_digest,
    validate_canonical_decision_handoff,
)

VECTOR_DIR = Path("docs/en/architecture/test-vectors/decision-to-bind-handoff-v1")
EVALUATED_AT = datetime(2030, 1, 1, 0, 0, 2, tzinfo=timezone.utc)


def _vectors() -> list[dict[str, object]]:
    return [json.loads(path.read_text()) for path in sorted(VECTOR_DIR.glob("vector-*.json"))]


def _binding(candidate: object, candidate_hash: str) -> CandidateHashBindingAssertion:
    """Build an explicitly synthetic, independently supplied test binding."""
    return CandidateHashBindingAssertion(
        candidate_value_digest=canonical_handoff_assertion_value_digest(candidate),
        asserted_candidate_hash=candidate_hash,
        candidate_hash_profile="synthetic-upstream-profile/v1",
        source_artifact_ref="candidate-fixture-001",
        source_hash="sha256:candidate-fixture-001",
        verification_mechanism="synthetic-independent-test-verifier",
        verified_at=EVALUATED_AT,
    )


def _complete_context(handoff: dict[str, object]) -> CanonicalDecisionHandoffValidationContext:
    """Build the deliberate positive-path synthetic context (never production)."""
    assertions = tuple(
        TrustedValueAssertion(
            field_path=record["field_path"],
            value_digest=canonical_handoff_assertion_value_digest(record["value"]),
            source_artifact_ref=record["source_artifact_ref"],
            source_hash=record.get("source_hash"),
            verification_mechanism="synthetic-independent-test-verifier",
            verified_at=EVALUATED_AT,
        )
        for record in handoff["provenance"]
    )
    return CanonicalDecisionHandoffValidationContext(
        value_assertions=assertions,
        candidate_hash_binding=_binding(handoff["candidate"], handoff["candidate_hash"]),
    )


def test_all_26_vectors_compute_declared_semantics_without_metadata() -> None:
    """Compute every result using only runtime input, context, and fixed time."""
    vectors = _vectors()
    baseline = next(vector for vector in vectors if vector["vector_id"] == "DTBH-V1-01")["input"]
    for vector in vectors:
        handoff = vector["input"]
        if vector["vector_id"] == "DTBH-V1-01":
            context = _complete_context(handoff)
        elif vector["vector_id"] == "DTBH-V1-05":
            context = CanonicalDecisionHandoffValidationContext(
                candidate_hash_binding=_binding(baseline["candidate"], baseline["candidate_hash"])
            )
        else:
            context = CanonicalDecisionHandoffValidationContext(
                candidate_hash_binding=_binding(handoff["candidate"], handoff["candidate_hash"])
            )
        result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
        assert result.status.value == vector["expected_handoff_status"], vector["vector_id"]
        assert [reason.value for reason in result.reason_codes] == vector["expected_reason_codes"], vector["vector_id"]


def test_ready_requires_independent_context_and_is_deterministic_and_immutable() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    # Filename sorting puts vector 01 first.
    assert handoff["handoff_id"] == "handoff-fixture-01"
    before = deepcopy(handoff)
    empty = validate_canonical_decision_handoff(
        handoff, CanonicalDecisionHandoffValidationContext(), EVALUATED_AT
    )
    assert empty.status is CanonicalDecisionHandoffStatus.INCOMPLETE
    assert empty.reason_codes == (CanonicalDecisionHandoffReasonCode.HANDOFF_PROVENANCE_UNVERIFIED,)
    context = _complete_context(handoff)
    first = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    second = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert first == second
    assert first.ready_for_guarded_promotion and not first.fail_closed
    assert handoff == before


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (("candidate", "actor_identity"), "HANDOFF_CANDIDATE_HASH_MISMATCH"),
        ((None, "candidate_hash"), "HANDOFF_CANDIDATE_HASH_MISMATCH"),
        (("authority_evidence", "issuer"), "HANDOFF_PROVENANCE_MISMATCH"),
        (("human_approval_evidence", "approver_identity"), "HANDOFF_PROVENANCE_MISMATCH"),
        (("policy_lineage", "version"), "HANDOFF_PROVENANCE_MISMATCH"),
        (("expected_state", "fingerprint"), "HANDOFF_PROVENANCE_MISMATCH"),
        (("trustlog_lineage", "chain_hash"), "HANDOFF_PROVENANCE_MISMATCH"),
        (("replay_lineage", "artifact_hash"), "HANDOFF_PROVENANCE_MISMATCH"),
    ],
)
def test_trusted_assertions_cannot_be_reused_after_substitution(mutation, reason) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    parent, key = mutation
    container = handoff if parent is None else handoff[parent]
    container[key] = f"modified:{container[key]}"
    result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert reason in {item.value for item in result.reason_codes}


def test_declared_metadata_never_drives_computed_security_state() -> None:
    negative = deepcopy(next(v["input"] for v in _vectors() if v["vector_id"] == "DTBH-V1-08"))
    negative["handoff_status"] = "READY_FOR_GUARDED_PROMOTION"
    negative["refusal_reason_codes"] = []
    result = validate_canonical_decision_handoff(
        negative,
        CanonicalDecisionHandoffValidationContext(candidate_hash_binding=_binding(negative["candidate"], negative["candidate_hash"])),
        EVALUATED_AT,
    )
    assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE
    assert not result.declared_status_matches
    assert not result.declared_reason_codes_match


@pytest.mark.parametrize("malformation", ["not_dict", "missing_candidate", "candidate_scalar", "action_scalar", "provenance_scalar", "duplicate_path", "bad_timestamp", "target_scalar"])
def test_malformed_untrusted_inputs_return_structured_invalid(malformation: str) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    if malformation == "not_dict":
        handoff = []
    elif malformation == "missing_candidate":
        del handoff["candidate"]
    elif malformation == "candidate_scalar":
        handoff["candidate"] = "candidate"
    elif malformation == "action_scalar":
        handoff["candidate"]["canonical_action"] = "transfer"
    elif malformation == "provenance_scalar":
        handoff["provenance"] = {}
    elif malformation == "duplicate_path":
        handoff["provenance"].append(deepcopy(handoff["provenance"][0]))
    elif malformation == "bad_timestamp":
        handoff["created_at"] = "2030-01-01T00:00:00"
    else:
        handoff["target_context"] = "target"
    result = validate_canonical_decision_handoff(
        handoff, CanonicalDecisionHandoffValidationContext(), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert not result.structure_valid and result.fail_closed


def test_runtime_schema_enums_are_coherent() -> None:
    schema = json.loads(Path("schemas/decision-to-bind-handoff-v1.schema.json").read_text())
    assert {item.value for item in CanonicalDecisionHandoffStatus} == set(schema["properties"]["handoff_status"]["enum"])
    assert {item.value for item in CanonicalDecisionHandoffReasonCode} == set(schema["properties"]["refusal_reason_codes"]["items"]["enum"])
    assert ASSERTION_VALUE_DIGEST_PROFILE == "veritas.canonical-handoff.assertion-value/v1"


def test_module_has_no_effectful_or_forbidden_imports() -> None:
    path = Path("veritas_os/policy/canonical_decision_handoff.py")
    tree = ast.parse(path.read_text())
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    source = path.read_text()
    assert not imported & {"requests", "httpx", "openai", "subprocess", "socket"}
    for forbidden in ("ExecutionIntent", "execute_bind", "WebhookBindAdapter", "open(", "write_text", "eval(", "exec(", "pickle"):
        assert forbidden not in source
