"""Contract tests for observable-digest resolver v1 formalization."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "observable_digest_resolver_contract_v1.schema.json"
DOC_PATH = ROOT / "docs" / "en" / "architecture" / "observable-digest-resolver-contract-v1.md"


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_contract_version_and_resolution_states_are_frozen() -> None:
    schema = _schema()
    assert schema["properties"]["contract_version"]["const"] == "1.0"
    result = schema["$defs"]["result"]
    assert result["properties"]["resolution_state"]["enum"] == [
        "RESOLVED",
        "UNRESOLVED",
    ]


def test_resolver_failure_predicates_are_bounded_to_existing_resolution_scope() -> None:
    schema = _schema()
    assert schema["$defs"]["failure_predicate"]["enum"] == [
        "LOCATOR_MISSING",
        "LOCATOR_MALFORMED",
        "RESOLUTION_FAILED",
        "AUTHZ_DENIED",
        "SCHEMA_MISMATCH",
        "UNKNOWN_TRANSIENT",
    ]

    resolver_predicates = set(schema["$defs"]["failure_predicate"]["enum"])
    assert "DIGEST_MISMATCH" not in resolver_predicates
    assert "BOUNDARY_VALIDATION_FAILURE" not in resolver_predicates
    assert "REPLAY_DUPLICATE" not in resolver_predicates
    assert "STALE_DIGEST" not in resolver_predicates


def test_non_amplification_guarantees_are_mandatory_false_constants() -> None:
    schema = _schema()
    guarantees = schema["$defs"]["semantic_guarantees"]
    required = {
        "authority_created",
        "execution_permission_changed",
        "digest_match_asserted",
        "boundary_validation_asserted",
        "uncertainty_erased",
        "remediation_executed",
    }
    assert set(guarantees["required"]) == required
    for field in required:
        assert guarantees["properties"][field] == {"const": False}


def test_request_does_not_accept_expected_digest_or_execution_semantics() -> None:
    schema = _schema()
    request_props = schema["$defs"]["request"]["properties"]
    assert set(request_props) == {
        "request_id",
        "locator",
        "caller_id_hash",
        "requested_at",
        "resolver_profile",
    }
    assert schema["$defs"]["request"]["additionalProperties"] is False


def test_result_surface_is_evidence_only_and_closed() -> None:
    schema = _schema()
    result = schema["$defs"]["result"]
    assert result["additionalProperties"] is False
    assert set(result["properties"]) == {
        "request_id",
        "locator",
        "resolver_id",
        "observed_at",
        "resolution_state",
        "resolved_digest",
        "evidence_ref",
        "failure_predicates",
        "semantic_guarantees",
    }

    forbidden = {
        "allow",
        "deny",
        "decision",
        "admissible",
        "authority",
        "human_approval",
        "bind_authorization",
        "execution_permission",
        "remediation",
        "expected_digest",
    }
    assert forbidden.isdisjoint(result["properties"])


def test_resolved_and_unresolved_shapes_preserve_evidence_boundary() -> None:
    schema = _schema()
    constraints = schema["$defs"]["result"]["allOf"]
    resolved = constraints[0]
    unresolved = constraints[1]

    assert resolved["if"]["properties"]["resolution_state"]["const"] == "RESOLVED"
    assert resolved["then"]["properties"]["failure_predicates"]["maxItems"] == 0
    assert unresolved["if"]["properties"]["resolution_state"]["const"] == "UNRESOLVED"
    assert unresolved["then"]["properties"]["resolved_digest"] == {"type": "null"}
    assert unresolved["then"]["properties"]["failure_predicates"]["minItems"] == 1


def test_documentation_explicitly_keeps_resolver_non_behavioral() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "Resolution Evidence\n!= Boundary Validation\n!= Admissibility\n!= Authority\n!= Execution Permission" in text
    assert "`RESOLVED` does **not** mean:" in text
    assert "This document does not approve a runtime resolver." in text
    assert "runtime resolver behavior remains absent" in text
    assert "resolver access authorized\n!= execution authorized" in text


def test_security_review_is_required_before_behavioral_activation() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    required_topics = [
        "SSRF",
        "tenant and scope isolation",
        "network egress restrictions",
        "timeout and bounded retry policy",
        "secret handling and redaction",
        "trust-root / authenticity handling",
        "no implicit fallback to unsafe locator types",
    ]
    for topic in required_topics:
        assert topic in text
