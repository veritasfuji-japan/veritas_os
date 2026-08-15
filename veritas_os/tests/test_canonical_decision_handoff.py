"""Runtime and adversarial tests for CanonicalDecisionHandoff v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from veritas_os.policy.canonical_decision_handoff import (
    ASSERTION_VALUE_DIGEST_PROFILE,
    CANONICAL_PROVENANCE_CLASSES,
    CANONICAL_VERIFICATION_STATUSES,
    HUMAN_APPROVAL_EXACT_OPERATION_CLAIM,
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
            claims=(HUMAN_APPROVAL_EXACT_OPERATION_CLAIM,)
            if record["field_path"] == "human_approval_evidence"
            else (),
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
    provenance_properties = schema["$defs"]["provenanceRecord"]["properties"]
    assert CANONICAL_PROVENANCE_CLASSES == frozenset(
        provenance_properties["provenance_class"]["enum"]
    )
    assert CANONICAL_VERIFICATION_STATUSES == frozenset(
        provenance_properties["verification_status"]["enum"]
    )
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


@pytest.mark.parametrize(
    "format_version",
    ["canonical-decision-handoff/v2", "", None, pytest.param("missing", id="missing")],
)
def test_format_version_confusion_is_structurally_invalid(format_version) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    if format_version == "missing":
        del handoff["format_version"]
    else:
        handoff["format_version"] = format_version
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,
    )


@pytest.mark.parametrize(
    "provenance_class", ["UNAVAILABLE", "UNVERIFIED_STRUCTURED_INPUT"]
)
def test_forbidden_ready_provenance_class_is_unverified(
    provenance_class: str,
) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    handoff["provenance"][0]["provenance_class"] = provenance_class
    result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_PROVENANCE_UNVERIFIED,
    )


@pytest.mark.parametrize(
    ("parent", "field", "value", "reason"),
    [
        (
            "authority_evidence",
            "issued_at",
            "2030-01-01T00:00:03Z",
            "HANDOFF_AUTHORITY_EVIDENCE_INVALID",
        ),
        (
            "human_approval_evidence",
            "approved_at",
            "2030-01-01T00:00:03Z",
            "HANDOFF_APPROVAL_EVIDENCE_INVALID",
        ),
        (
            "source_decision",
            "canonical_decision_ts",
            "2030-01-01T00:00:03Z",
            "HANDOFF_SCHEMA_INVALID",
        ),
        (None, "created_at", "2030-01-01T00:00:03Z", "HANDOFF_SCHEMA_INVALID"),
    ],
)
def test_future_security_material_is_not_yet_valid(parent, field, value, reason) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    container = handoff if parent is None else handoff[parent]
    container[field] = value
    result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert reason in {item.value for item in result.reason_codes}


def test_future_trusted_assertions_do_not_satisfy_readiness() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    future = datetime(2030, 1, 1, 0, 0, 3, tzinfo=timezone.utc)
    value_context = replace(
        context,
        value_assertions=(
            replace(context.value_assertions[0], verified_at=future),
            *context.value_assertions[1:],
        ),
    )
    binding_context = replace(
        context,
        candidate_hash_binding=replace(
            context.candidate_hash_binding, verified_at=future
        ),
    )
    for future_context in (value_context, binding_context):
        result = validate_canonical_decision_handoff(
            handoff, future_context, EVALUATED_AT
        )
        assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE
        assert result.reason_codes == (
            CanonicalDecisionHandoffReasonCode.HANDOFF_PROVENANCE_UNVERIFIED,
        )


@pytest.mark.parametrize("requirement", ["authority_requirement", "human_approval_requirement"])
@pytest.mark.parametrize("field", ["resolved", "required"])
@pytest.mark.parametrize("value", ["true", "false", 1, None, pytest.param("missing", id="missing")])
def test_requirement_boolean_type_confusion_is_invalid(
    requirement: str, field: str, value: object
) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    if value == "missing":
        del handoff[requirement][field]
    else:
        handoff[requirement][field] = value
    if field == "required":
        evidence = (
            "authority_evidence"
            if requirement == "authority_requirement"
            else "human_approval_evidence"
        )
        handoff[evidence] = None
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,
    )


def test_human_approval_requires_trusted_exact_operation_claim() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    approval_index = next(
        index
        for index, assertion in enumerate(context.value_assertions)
        if assertion.field_path == "human_approval_evidence"
    )
    assertions = list(context.value_assertions)
    assertions[approval_index] = replace(assertions[approval_index], claims=())
    missing_claim = replace(context, value_assertions=tuple(assertions))
    result = validate_canonical_decision_handoff(
        handoff, missing_claim, EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE
    assert validate_canonical_decision_handoff(
        handoff, context, EVALUATED_AT
    ).ready_for_guarded_promotion

    handoff["human_approval_evidence"]["approval_scope"] = "opaque:changed"
    result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_PROVENANCE_MISMATCH,
    )


@pytest.mark.parametrize(
    ("parent", "field"),
    [
        ("source_decision", "request_id"),
        (None, "candidate_hash"),
        ("candidate", "candidate_id"),
    ],
)
def test_empty_critical_identifiers_cannot_be_trusted(parent, field) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    container = handoff if parent is None else handoff[parent]
    container[field] = ""
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID


def test_candidate_binding_requires_nonempty_profile() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    context = _complete_context(handoff)
    context = replace(
        context,
        candidate_hash_binding=replace(
            context.candidate_hash_binding, candidate_hash_profile=""
        ),
    )
    result = validate_canonical_decision_handoff(handoff, context, EVALUATED_AT)
    assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE


def test_expired_handoff_is_invalid() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    handoff["expires_at"] = "2030-01-01T00:00:01Z"
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_EXPIRED,
    )


def test_invalid_evidence_outranks_stale_policy_review() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    handoff["authority_evidence"]["actor_identity"] = "actor:other"
    handoff["policy_lineage"]["superseded"] = True
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_AUTHORITY_EVIDENCE_INVALID,
    )


@pytest.mark.parametrize(
    ("field_path", "malformed_value"),
    [
        ("authority_evidence", "verified"),
        ("human_approval_evidence", []),
        ("policy_lineage", "policy"),
        ("expected_state", 123),
    ],
)
def test_trusted_context_cannot_legitimize_malformed_nullable_object(
    field_path: str, malformed_value: object
) -> None:
    """Reject object-or-null violations before consulting trusted context."""
    handoff = deepcopy(_vectors()[0]["input"])
    handoff[field_path] = malformed_value
    record = next(
        record
        for record in handoff["provenance"]
        if record["field_path"] == field_path
    )
    record["value"] = malformed_value
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,
    )
    assert not result.structure_valid


@pytest.mark.parametrize(
    ("record_field", "value"),
    [
        ("provenance_class", "UNKNOWN_CLASS"),
        ("provenance_class", 1),
        ("verification_status", "UNKNOWN_STATUS"),
        ("verification_status", []),
    ],
)
def test_provenance_vocabularies_are_structurally_closed(
    record_field: str, value: object
) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    handoff["provenance"][0][record_field] = value
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,
    )
    assert not result.structure_valid


@pytest.mark.parametrize(
    "request_path",
    ["source_decision", "trustlog_lineage", "replay_lineage"],
)
@pytest.mark.parametrize("value", [[], {}, 1, None, ""])
def test_malformed_request_ids_return_structured_invalid(
    request_path: str, value: object
) -> None:
    """Never hash attacker-controlled request identifiers in a set."""
    handoff = deepcopy(_vectors()[0]["input"])
    handoff[request_path]["request_id"] = value
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_SCHEMA_INVALID,
    )
    assert not result.structure_valid


def test_unresolved_approval_requirement_outranks_missing_evidence() -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    handoff["human_approval_requirement"]["resolved"] = False
    handoff["human_approval_evidence"] = None
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INCOMPLETE
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_APPROVAL_REQUIREMENT_UNRESOLVED,
    )


def test_intrinsic_target_invalid_is_not_masked_by_future_binding() -> None:
    vector = next(
        vector for vector in _vectors() if vector["vector_id"] == "DTBH-V1-24"
    )
    handoff = deepcopy(vector["input"])
    future_binding = replace(
        _binding(handoff["candidate"], handoff["candidate_hash"]),
        verified_at=datetime(2030, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
    )
    result = validate_canonical_decision_handoff(
        handoff,
        CanonicalDecisionHandoffValidationContext(
            candidate_hash_binding=future_binding
        ),
        EVALUATED_AT,
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert result.reason_codes == (
        CanonicalDecisionHandoffReasonCode.HANDOFF_TARGET_CONTEXT_MISMATCH,
    )


@pytest.mark.parametrize("handoff_id", ["", None, 1, pytest.param("missing")])
def test_handoff_id_is_required_artifact_identity(handoff_id: object) -> None:
    handoff = deepcopy(_vectors()[0]["input"])
    if handoff_id == "missing":
        del handoff["handoff_id"]
    else:
        handoff["handoff_id"] = handoff_id
    result = validate_canonical_decision_handoff(
        handoff, _complete_context(handoff), EVALUATED_AT
    )
    assert result.status is CanonicalDecisionHandoffStatus.INVALID
    assert not result.structure_valid
