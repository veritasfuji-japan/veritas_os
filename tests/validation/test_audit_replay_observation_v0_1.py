"""Synthetic checks for the proposed offline replay observation contract.

These are format/integrity tests, not tests of a persistent store or an
authorization single-use boundary.
"""

from __future__ import annotations

from copy import deepcopy
import json

import pytest
from jsonschema import Draft202012Validator

from scripts.validation.validate_audit_replay_observation_v0_1 import (
    SCHEMA,
    calculate_observation_hash,
    verify_observation_contract,
)


def synthetic_observation() -> dict:
    record = {
        "format_version": "veritas.audit-replay-observation/0.1",
        "record_type": "LOCAL_AUDIT_OBSERVATION",
        "packet_id": "synthetic-packet-1",
        "case_id": "synthetic-case-1",
        "repository_claim": "Example/Audit",
        "repository_key": "example/audit",
        "source_commit": "1" * 40,
        "operation_id": "op-1",
        "manifest_id": "ecm-op-1",
        "profile_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "snapshot_digest": "c" * 64,
        "local_manifest_binding": "MATCHED",
        "declared_provenance_binding": "CLAIMED_CONTEXT_MATCHES_LOCAL_MANIFEST",
        "origin_authentication": "NOT_PERFORMED",
        "independent_review": "NOT_PERFORMED",
    }
    record["record_hash"] = calculate_observation_hash(record)
    return record


def test_schema_is_draft_2020_12_valid():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_valid_synthetic_candidate_is_only_locally_consistent():
    record = synthetic_observation()
    assert verify_observation_contract(record) == []
    assert record["origin_authentication"] == "NOT_PERFORMED"
    assert record["independent_review"] == "NOT_PERFORMED"


def test_identical_candidate_is_deterministic():
    a = synthetic_observation()
    b = deepcopy(a)
    assert a["record_hash"] == b["record_hash"]
    assert verify_observation_contract(b) == []


def test_modified_candidate_without_new_digest_is_rejected():
    record = synthetic_observation()
    record["operation_id"] = "op-tampered"
    assert "RECORD_HASH_MISMATCH" in verify_observation_contract(record)


def test_claimed_repository_namespace_mismatch_is_rejected_even_if_rehashed():
    record = synthetic_observation()
    record["repository_key"] = "example/other"
    record["record_hash"] = calculate_observation_hash(record)
    assert "REPOSITORY_NAMESPACE_MISMATCH" in verify_observation_contract(record)


def test_ascii_casefolded_repository_claim_is_valid_with_matching_hash():
    record = synthetic_observation()
    record["repository_claim"] = "EXAMPLE/AUDIT"
    record["record_hash"] = calculate_observation_hash(record)
    assert verify_observation_contract(record) == []


@pytest.mark.parametrize("field,value", [
    ("record_type", "RUNTIME_AUTHORIZATION"),
    ("format_version", "veritas.audit-replay-observation/0.2"),
    ("origin_authentication", "VERIFIED"),
    ("independent_review", "ACCEPTED"),
    ("local_manifest_binding", "AUTHORIZED"),
    ("declared_provenance_binding", "ORIGIN_AUTHENTICATED"),
    ("profile_sha256", 7),
    ("manifest_sha256", "B" * 64),
    ("snapshot_digest", "c" * 63),
    ("source_commit", "0" * 64),
    ("repository_claim", "example/..\\evil"),
    ("repository_claim", "example/target"),
    ("repository_key", "EXAMPLE/AUDIT"),
    ("case_id", []),
    ("operation_id", {"id": "op-1"}),
    ("persisted", True),
])
def test_invalid_claims_and_fields_rejected_even_with_consistent_digest(field, value):
    record = synthetic_observation()
    record[field] = value
    record["record_hash"] = calculate_observation_hash(record)
    assert verify_observation_contract(record), field


@pytest.mark.parametrize("field", [
    "manifest_id", "packet_id", "operation_id", "case_id",
])
def test_whitespace_only_or_padded_identifiers_rejected_when_rehashed(field):
    record = synthetic_observation()
    record[field] = " invalid "
    record["record_hash"] = calculate_observation_hash(record)
    assert "INVALID_ID_VALUE" in verify_observation_contract(record)


@pytest.mark.parametrize("invalid", [None, [], "not-an-object", 2])
def test_non_object_is_rejected_without_exception(invalid):
    assert verify_observation_contract(invalid) == ["SCHEMA_INVALID"]


def test_missing_digest_and_unknown_authority_fields_rejected():
    record = synthetic_observation()
    del record["record_hash"]
    assert verify_observation_contract(record) == ["SCHEMA_INVALID"]
    record = synthetic_observation()
    record["authorization_consumed"] = True
    record["record_hash"] = calculate_observation_hash(record)
    assert verify_observation_contract(record) == ["SCHEMA_INVALID"]
