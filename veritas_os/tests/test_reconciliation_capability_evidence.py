"""Tests for the non-enforcing reconciliation capability artifact."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from veritas_os.governance.reconciliation_capability_evidence import (
    ReconciliationCapabilityClass,
    ReconciliationCapabilityEvidence,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64


def _query_payload() -> dict[str, object]:
    return {
        "evidence_id": "rce-001",
        "target_id": "payments-sandbox",
        "endpoint_identity_binding_digest": _HASH_A,
        "target_configuration_digest": _HASH_B,
        "capability_class": ReconciliationCapabilityClass.AUTHORITATIVE_QUERY,
        "correlation_identity_type": "idempotency_key",
        "correlation_identity_pre_dispatch": True,
        "correlation_identity_caller_controlled": True,
        "exact_attempt_lookup_available": True,
        "exact_lineage_binding_supported": True,
        "downstream_durability_supported": True,
        "non_mutating_observation_supported": True,
        "authoritative_evidence_available": False,
        "source_type": "target_capability_assessment",
        "source_identity": "assessment:payments-sandbox:v1",
        "source_digest": _HASH_C,
        "verifier_id": "reconciliation-capability-verifier/v1",
        "verifier_policy_id": "reconciliation-capability-policy/v1",
        "verifier_policy_hash": _HASH_D,
        "assessed_at": "2026-09-18T00:00:00Z",
        "valid_until": "2026-10-18T00:00:00Z",
        "metadata": {"environment": "sandbox"},
    }


def test_authoritative_query_artifact_is_non_authorizing_and_stable() -> None:
    artifact = ReconciliationCapabilityEvidence(**_query_payload())
    clone = ReconciliationCapabilityEvidence(**_query_payload())

    assert artifact.execution_eligibility_decision_created is False
    assert artifact.execution_permission_created is False
    assert artifact.retry_permission_created is False
    assert artifact.terminal_effect_claim_created is False
    assert artifact.deterministic_digest() == clone.deterministic_digest()

    changed = _query_payload()
    changed["target_configuration_digest"] = "e" * 64
    assert (
        ReconciliationCapabilityEvidence(**changed).deterministic_digest()
        != artifact.deterministic_digest()
    )


def test_authoritative_evidence_does_not_require_query_api() -> None:
    payload = _query_payload()
    payload.update(
        {
            "capability_class": ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE,
            "correlation_identity_type": None,
            "correlation_identity_pre_dispatch": False,
            "correlation_identity_caller_controlled": False,
            "exact_attempt_lookup_available": False,
            "authoritative_evidence_available": True,
        }
    )

    artifact = ReconciliationCapabilityEvidence(**payload)
    assert artifact.capability_class is ReconciliationCapabilityClass.AUTHORITATIVE_EVIDENCE


def test_authoritative_query_requires_predispatch_exact_lookup() -> None:
    payload = _query_payload()
    payload["correlation_identity_pre_dispatch"] = False

    with pytest.raises(ValueError, match="reconciliation_capability_authoritative_query_invalid"):
        ReconciliationCapabilityEvidence(**payload)


def test_authoritative_class_requires_verifier_binding() -> None:
    payload = _query_payload()
    payload["verifier_id"] = None
    payload["verifier_policy_id"] = None
    payload["verifier_policy_hash"] = None

    with pytest.raises(
        ValueError,
        match="reconciliation_capability_authoritative_verifier_missing",
    ):
        ReconciliationCapabilityEvidence(**payload)


def test_heuristic_only_cannot_claim_authoritative_surface() -> None:
    payload = _query_payload()
    payload.update(
        {
            "capability_class": ReconciliationCapabilityClass.HEURISTIC_ONLY,
            "correlation_identity_type": None,
            "correlation_identity_pre_dispatch": False,
            "correlation_identity_caller_controlled": False,
            "exact_attempt_lookup_available": True,
            "exact_lineage_binding_supported": False,
            "downstream_durability_supported": False,
            "non_mutating_observation_supported": False,
            "authoritative_evidence_available": False,
            "verifier_id": None,
            "verifier_policy_id": None,
            "verifier_policy_hash": None,
        }
    )

    with pytest.raises(ValueError, match="reconciliation_capability_heuristic_class_conflict"):
        ReconciliationCapabilityEvidence(**payload)


def test_unavailable_or_unverified_can_record_absence_without_creating_permission() -> None:
    payload = _query_payload()
    payload.update(
        {
            "capability_class": ReconciliationCapabilityClass.UNAVAILABLE_OR_UNVERIFIED,
            "correlation_identity_type": None,
            "correlation_identity_pre_dispatch": False,
            "correlation_identity_caller_controlled": False,
            "exact_attempt_lookup_available": False,
            "exact_lineage_binding_supported": False,
            "downstream_durability_supported": False,
            "non_mutating_observation_supported": False,
            "authoritative_evidence_available": False,
            "verifier_id": None,
            "verifier_policy_id": None,
            "verifier_policy_hash": None,
        }
    )

    artifact = ReconciliationCapabilityEvidence(**payload)
    assert artifact.capability_class is ReconciliationCapabilityClass.UNAVAILABLE_OR_UNVERIFIED
    assert artifact.retry_permission_created is False


def test_valid_until_must_follow_assessment() -> None:
    payload = _query_payload()
    payload["valid_until"] = payload["assessed_at"]

    with pytest.raises(
        ValueError,
        match="reconciliation_capability_valid_until_not_after_assessed_at",
    ):
        ReconciliationCapabilityEvidence(**payload)


def test_committed_schema_matches_model_and_validates_artifact() -> None:
    artifact = ReconciliationCapabilityEvidence(**_query_payload())
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "schemas/reconciliation-capability-evidence-v1.schema.json"
        ).read_text()
    )
    expected = ReconciliationCapabilityEvidence.model_json_schema()

    assert {key: value for key, value in schema.items() if key != "$schema"} == expected
    Draft202012Validator(schema).validate(artifact.model_dump(mode="json"))


def test_extra_fields_and_permission_flags_fail_closed() -> None:
    extra = deepcopy(_query_payload())
    extra["unexpected"] = True
    with pytest.raises(ValueError):
        ReconciliationCapabilityEvidence(**extra)

    elevated = _query_payload()
    elevated["execution_permission_created"] = True
    with pytest.raises(ValueError):
        ReconciliationCapabilityEvidence(**elevated)
