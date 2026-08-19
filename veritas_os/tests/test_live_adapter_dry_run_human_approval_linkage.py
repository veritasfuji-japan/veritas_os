"""Integrity, linkage, and non-effect tests for Human Approval review v1."""

from __future__ import annotations

import ast
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from veritas_os.policy.live_adapter_dry_run_human_approval_linkage import (
    BIND_REQUIREMENTS,
    CHECK_NAMES,
    EFFECT_FIELDS,
    SCOPE_LIMITATIONS,
    LiveAdapterDryRunHumanApprovalLinkageError,
    _packet_hash,
    build_live_adapter_dry_run_human_approval_linkage_review_packet,
    verify_live_adapter_dry_run_human_approval_linkage_review_packet,
)
from veritas_os.tests.test_live_adapter_dry_run_authority_evidence_linkage import (
    RECORDED_AT as SOURCE_RECORDED_AT,
    _packet as source_packet,
)

RECORDED_AT = SOURCE_RECORDED_AT + timedelta(seconds=1)
DEFAULT_SOURCE = source_packet()
MODULE = Path(
    "veritas_os/policy/live_adapter_dry_run_human_approval_linkage.py"
)
SCHEMA = Path(
    "schemas/live-adapter-dry-run-human-approval-linkage-v1.schema.json"
)


def _reference(source=None, **changes):
    source = source or DEFAULT_SOURCE
    value = {
        "human_approval_reference_id": "approval-ref:billing:v1",
        "approval_source_type": "upstream-artifact",
        "approval_source_id": "approval-source:billing:v1",
        "approver_id": "operator:alice",
        "approver_role": "billing-operator",
        "approval_scope": "billing-dispatch",
        "approval_subject": "billing-request",
        "approval_reason": "declared dry-run review",
        "approval_issued_at": (RECORDED_AT - timedelta(days=1)).isoformat(),
        "approval_expires_at": (RECORDED_AT + timedelta(days=1)).isoformat(),
        "approval_evidence_hash": "sha256:declared-metadata-only",
        "approval_evidence_format": "declared-reference/v1",
        "declared_approval_state": "DECLARED_APPROVED_BY_UPSTREAM_ARTIFACT",
        "linked_execution_intent_id": source.execution_intent_id,
        "linked_adapter_contract_id": source.adapter_contract_id,
        "linked_endpoint_candidate_id": source.endpoint_candidate[
            "endpoint_candidate_id"
        ],
        "linked_credential_reference_id": source.credential_reference[
            "credential_reference_id"
        ],
        "linked_target_system": source.credential_reference["target_system"],
        "linked_target_resource_scope": source.credential_reference[
            "target_resource_scope"
        ],
        "linked_purpose": source.credential_reference["credential_purpose"],
        "linked_authority_evidence_reference_ids": [
            reference.authority_evidence_reference_id
            for reference in source.authority_evidence_reference_bundle
            .authority_evidence_references
        ],
    }
    value.update(changes)
    return value


def _bundle(source=None, references=None, **changes):
    source = source or DEFAULT_SOURCE
    value = {
        "human_approval_reference_bundle_id": "authority-bundle:billing:v1",
        "bundle_declared_by": "operator:alice",
        "bundle_declared_at": RECORDED_AT.isoformat(),
        "bundle_scope": ["billing-dispatch"],
        "human_approval_references": (
            [_reference(source)] if references is None else references
        ),
        "human_approval_binding_claims": [],
        "bundle_limitations": ["metadata-only", "no-external-verification"],
    }
    value.update(changes)
    return value


def _packet(*, source=None, bundle=None, semantic_match=False):
    source = source or (
        source_packet(semantic_match=True) if semantic_match else DEFAULT_SOURCE
    )
    return build_live_adapter_dry_run_human_approval_linkage_review_packet(
        source, bundle or _bundle(source), RECORDED_AT
    )


def _rehash(raw):
    digest = _packet_hash(raw)
    raw["live_adapter_dry_run_human_approval_linkage_review_hash"] = digest
    raw["live_adapter_dry_run_human_approval_linkage_review_id"] = (
        f"ladhal:v1:sha256:{digest}"
    )


def test_builder_creates_verified_exactly_linked_packet(monkeypatch) -> None:
    import veritas_os.policy.live_adapter_dry_run_human_approval_linkage as module

    actual = module.verify_live_adapter_dry_run_authority_evidence_linkage_review_packet
    calls = []

    def recording(value):
        calls.append(value)
        return actual(value)

    monkeypatch.setattr(
        module, "verify_live_adapter_dry_run_authority_evidence_linkage_review_packet",
        recording,
    )
    packet = module.build_live_adapter_dry_run_human_approval_linkage_review_packet(
        source_packet(), _bundle(), RECORDED_AT
    )
    assert len(calls) == 2
    assert module.verify_live_adapter_dry_run_human_approval_linkage_review_packet(
        packet
    ) == packet
    assert len(calls) == 3
    assert not packet.fail_closed
    assert packet.human_approval_state == "NOT_APPROVED"
    assert packet.human_approval_linkage_result.all_approval_references_structurally_linked


@pytest.mark.parametrize("change", [
    {"unexpected": True}, {"human_approval_references": []},
    {"bundle_scope": ["missing-scope"]},
])
def test_bundle_is_closed_and_required_references_cover_scope(change) -> None:
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        _packet(bundle=_bundle(**change))


def test_duplicate_reference_ids_fail_closed() -> None:
    reference = _reference()
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        _packet(bundle=_bundle(references=[reference, reference]))


@pytest.mark.parametrize("state", [
    "DECLARED_PENDING_EXTERNAL_APPROVAL_VERIFICATION",
    "DECLARED_REJECTED_BY_UPSTREAM_ARTIFACT",
])
def test_non_verified_declared_state_fails_closed(state) -> None:
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        _packet(bundle=_bundle(references=[_reference(
            declared_approval_state=state
        )]))


def test_expired_reference_fails_closed() -> None:
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        _packet(bundle=_bundle(references=[_reference(
            approval_expires_at=RECORDED_AT.isoformat()
        )]))


@pytest.mark.parametrize("field", [
    "linked_execution_intent_id", "linked_adapter_contract_id",
    "linked_endpoint_candidate_id", "linked_credential_reference_id",
    "linked_target_system", "linked_target_resource_scope", "linked_purpose",
    "linked_authority_evidence_reference_ids",
])
def test_every_structural_link_requires_exact_match(field) -> None:
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        _packet(bundle=_bundle(references=[_reference(**{field: "mismatch"})]))


def test_source_fields_lineage_and_semantic_match_are_preserved() -> None:
    source = source_packet(semantic_match=True)
    packet = _packet(source=source)
    raw = source.model_dump(mode="json")
    for field in (
        "request_descriptor", "execution_intent", "execution_intent_id",
        "execution_intent_hash", "adapter_contract_descriptor",
        "adapter_contract_id", "adapter_contract_hash", "adapter_contract_version",
        "endpoint_candidate", "endpoint_identity_binding", "credential_reference",
        "credential_scope_binding", "bind_pre_dispatch_review_decision",
        "source_to_execution_intent_mapping", "field_mapping_proof",
        "required_field_presence", "source_decision_identity", "candidate_identity",
        "evidence_lineage", "replay_summary",
    ):
        actual = getattr(packet, field)
        if hasattr(actual, "model_dump"):
            actual = actual.model_dump(mode="json")
        assert actual == raw[field]
    assert packet.replay_summary["semantic_match"] is True
    assert not packet.human_approval_linkage_result.semantic_match_used
    assert not packet.human_approval_created


def test_checks_matrix_requirements_and_limitations_are_deterministic() -> None:
    first = _packet()
    second = _packet()
    assert first == second
    assert tuple(check.name for check in first.human_approval_linkage_checks) == (
        CHECK_NAMES
    )
    assert all(
        check.ordinal == ordinal and not any(
            getattr(check, field) for field in EFFECT_FIELDS
        )
        for ordinal, check in enumerate(first.human_approval_linkage_checks, 1)
    )
    assert tuple(x.name for x in first.future_bind_authorization_requirements) == (
        BIND_REQUIREMENTS
    )
    assert first.scope_limitations == SCOPE_LIMITATIONS


@pytest.mark.parametrize("field", [
    "source_authority_evidence_linkage_review_packet", "human_approval_reference_bundle",
    "human_approval_binding_matrix", "human_approval_linkage_result",
    "human_approval_linkage_checks",
    "future_bind_authorization_requirements", "scope_limitations",
])
def test_mutated_content_is_rejected_even_after_outer_rehash(field) -> None:
    raw = _packet().model_dump(mode="json")
    if field == "source_authority_evidence_linkage_review_packet":
        raw[field]["request_descriptor"]["purpose"] = "forged"
    elif field == "human_approval_reference_bundle":
        raw[field]["bundle_declared_by"] = "forged"
    elif field == "human_approval_binding_matrix":
        raw[field][0]["actual_value"] = "forged"
    elif field == "human_approval_linkage_result":
        raw[field]["all_approval_references_structurally_linked"] = False
    elif field == "human_approval_linkage_checks":
        raw[field][0]["evidence_ref"] = "forged"
    elif field.startswith("future_"):
        raw[field][0]["name"] = "forged"
    else:
        raw[field].reverse()
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        verify_live_adapter_dry_run_human_approval_linkage_review_packet(raw)


@pytest.mark.parametrize("field,value", [
    ("fail_closed", True), ("human_approval_created", True),
    ("human_approval_created", True), ("authority_evidence_created", True),
    ("execution_authority_created", True),
    ("bind_authorization_created", True),
])
def test_authority_or_fail_closed_mutation_is_rejected(field, value) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = value
    _rehash(raw)
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        verify_live_adapter_dry_run_human_approval_linkage_review_packet(raw)


@pytest.mark.parametrize("field", [
    "live_adapter_dry_run_human_approval_linkage_review_id",
    "live_adapter_dry_run_human_approval_linkage_review_hash",
])
def test_forged_content_address_is_rejected(field) -> None:
    raw = _packet().model_dump(mode="json")
    raw[field] = "forged"
    with pytest.raises(LiveAdapterDryRunHumanApprovalLinkageError):
        verify_live_adapter_dry_run_human_approval_linkage_review_packet(raw)


def test_schema_validates_packet_and_rejects_mutation() -> None:
    schema = json.loads(SCHEMA.read_text())
    raw = _packet().model_dump(mode="json")
    Draft202012Validator(schema).validate(raw)
    raw["human_approval_created"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(raw)


def test_module_has_no_prohibited_imports_or_calls() -> None:
    tree = ast.parse(MODULE.read_text())
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports.intersection({
        "requests", "httpx", "urllib", "socket", "dns", "subprocess", "os",
        "pathlib",
    })
    text = MODULE.read_text()
    for prohibited in (
        "WebhookBindAdapter", "BindReceipt", "TrustLog", "open(", "os.environ",
        "read_text", "write_text", "credential_store", "verify_postconditions",
        "revert(", "apply(",
    ):
        assert prohibited not in text


def test_packet_hash_changes_with_content() -> None:
    raw = _packet().model_dump(mode="json")
    before = _packet_hash(raw)
    changed = deepcopy(raw)
    changed["human_approval_linkage_review_recorded_at"] = (
        RECORDED_AT + timedelta(seconds=1)
    ).isoformat()
    assert _packet_hash(changed) != before
