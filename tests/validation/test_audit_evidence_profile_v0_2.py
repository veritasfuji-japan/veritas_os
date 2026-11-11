"""Contract tests for strict Audit Evidence Profile v0.2 local bindings.

v0.1 remains accepted unchanged. All samples are synthetic and do not
authenticate any real-world execution, authority, origin or independent review.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.validation.validate_audit_evidence_profile import (
    V01_PROFILE_VERSION,
    V02_PROFILE_VERSION,
    verify,
)

ROOT = Path(__file__).resolve().parents[2]
V01 = ROOT / "tests/validation/fixtures/synthetic_example.json"
V02 = ROOT / "tests/validation/fixtures/synthetic_v0_2_example.json"


def fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bound_profile() -> dict:
    obj = fixture(V02)
    obj["cases"][0].update({
        "operation_id": "operation-1",
        "manifest_id": "ecm-operation-1",
        "manifest_evidence_id": "EV-1",
    })
    return obj


def assert_rejected(obj: dict, reason: str) -> None:
    issues = verify(obj, V02)
    assert any(reason in issue for issue in issues), issues


def test_v02_synthetic_fixture_valid_with_no_execution():
    obj = fixture(V02)
    assert obj["profile_version"] == V02_PROFILE_VERSION
    assert verify(obj, V02) == []


def test_v01_synthetic_fixture_still_valid():
    obj = fixture(V01)
    assert obj["profile_version"] == V01_PROFILE_VERSION
    assert verify(obj, V01) == []


def test_v02_explicit_nonexecuted_binding_can_be_structurally_valid():
    # Merely structural: evidence item EV-1 is not a chain manifest,
    # so this case would not be eligible for a successful Bridge report.
    assert verify(bound_profile(), V02) == []


def test_v01_rejects_v02_only_case_fields():
    obj = fixture(V01)
    obj["cases"][0]["operation_id"] = None
    assert verify(obj, V01)


@pytest.mark.parametrize("field", [
    "operation_id", "manifest_id", "manifest_evidence_id",
])
def test_v02_case_binding_field_is_required(field):
    obj = bound_profile()
    del obj["cases"][0][field]
    assert_rejected(obj, "SCHEMA")


@pytest.mark.parametrize("field", [
    "operation_id", "manifest_id", "manifest_evidence_id",
])
def test_v02_partial_case_binding_rejected(field):
    obj = bound_profile()
    obj["cases"][0][field] = None
    assert_rejected(obj, "PARTIAL_CASE_OPERATION_BINDING")


def test_v02_executed_case_cannot_have_null_binding():
    obj = fixture(V02)
    obj["scope"]["execution_performed"] = True
    obj["cases"][0]["observed"] = "PASS"
    obj["cases"][0]["expectation"] = "ALLOW"
    obj["cases"][0]["actual_effect"] = "ALLOWED"
    assert_rejected(obj, "SCHEMA")


@pytest.mark.parametrize("field,reason", [
    ("operation_id", "DUPLICATE_OPERATION_ID"),
    ("manifest_id", "DUPLICATE_MANIFEST_ID"),
    ("manifest_evidence_id", "DUPLICATE_MANIFEST_EVIDENCE_ID"),
])
def test_v02_identity_reuse_across_cases_rejected(field,reason):
    obj = bound_profile()
    other = deepcopy(obj["cases"][0])
    other["case_id"] = "CASE-OTHER"
    other["operation_id"] = "operation-2"
    other["manifest_id"] = "ecm-operation-2"
    other["manifest_evidence_id"] = "EV-2"
    if field == "operation_id":
        other[field] = obj["cases"][0][field]
    elif field == "manifest_id":
        other[field] = obj["cases"][0][field]
    else:
        other[field] = obj["cases"][0][field]
    obj["cases"].append(other)
    assert_rejected(obj, reason)


def test_v02_manifest_evidence_must_be_case_local():
    obj = bound_profile()
    obj["cases"][0]["evidence_ids"] = []
    assert_rejected(obj, "MANIFEST_NOT_LINKED_TO_CASE")


def test_v02_manifest_evidence_must_exist_in_evidence_inventory():
    obj = bound_profile()
    obj["cases"][0]["manifest_evidence_id"] = "EV-NOT-IN-INVENTORY"
    obj["cases"][0]["evidence_ids"].append("EV-NOT-IN-INVENTORY")
    assert_rejected(obj, "UNRESOLVED_CASE_MANIFEST_EVIDENCE")


def test_v02_refuses_legacy_profile_without_new_case_fields():
    obj = fixture(V01)
    obj["profile_version"] = V02_PROFILE_VERSION
    assert_rejected(obj, "SCHEMA")


def test_unknown_profile_version_fails_closed():
    obj = fixture(V02)
    obj["profile_version"] = "veritas.audit-evidence-profile/999"
    assert verify(obj, V02) == ["UNSUPPORTED_PROFILE_VERSION"]


def test_v02_rejects_extra_unrecognized_field():
    obj = fixture(V02)
    obj["cases"][0]["runtime_certification"] = True
    assert_rejected(obj, "SCHEMA")


def test_v02_does_not_promote_self_claimed_external_acceptance():
    obj = fixture(V02)
    obj["review"]["handoff_status"] = "REVIEWABLE"
    obj["review"]["reviewer_verdict"] = "ACCEPT"
    assert_rejected(obj, "UNVERIFIED_REVIEWABLE_HANDOFF")


def test_v02_rejects_local_evidence_hash_mismatch():
    obj = fixture(V02)
    obj["evidence"][0]["sha256"] = "f" * 64
    assert_rejected(obj, "EVIDENCE_HASH_MISMATCH")
