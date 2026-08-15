"""Canonical Decision Artifact to TrustLog exact-link tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from veritas_os.api.schemas import DecideResponse
from veritas_os.audit.canonical_decision_trust_link import (
    CanonicalDecisionTrustLinkError,
    CanonicalDecisionTrustLinkReason,
    build_canonical_decision_reference,
    record_canonical_decision_trust_link,
    verify_canonical_decision_trust_entry,
)
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)

ROOT = Path(__file__).resolve().parents[2]
VECTOR = (
    ROOT
    / "docs/en/architecture/test-vectors/canonical-decision-artifact-v1/vector-01.json"
)


def _artifact():
    vector = json.loads(VECTOR.read_text())
    source = DecideResponse.model_validate(vector["source_projection"])
    return build_canonical_decision_artifact(
        source,
        decision_ts=datetime(2031, 2, 3, 4, 5, 6, 123456, tzinfo=timezone.utc),
    )


def _append(event):
    return {
        **event,
        "created_at": "2031-02-03T04:05:07+00:00",
        "sha256_prev": None,
        "sha256": "a" * 64,
    }


def test_record_builds_exact_reference_and_domain_separated_receipt() -> None:
    artifact = _artifact()
    reference = build_canonical_decision_reference(artifact)
    receipt = record_canonical_decision_trust_link(
        artifact, append_trust_log_fn=_append
    )
    entry = _append(
        {
            "event_type": "canonical_decision_link",
            "audit_schema_version": "canonical_decision_trust_link/v1",
            "request_id": artifact.request_id,
            "pipeline_phase": "post_persistence_drift_verified",
            "canonical_decision_ref": reference.model_dump(mode="json"),
        }
    )

    assert reference.request_id == artifact.request_id
    assert receipt.canonical_decision_hash == artifact.decision_hash
    assert receipt.trust_log_entry_sha256 != artifact.decision_hash
    assert verify_canonical_decision_trust_entry(artifact, receipt, entry).ok


@pytest.mark.parametrize("field", ["decision_hash", "decision_id", "decision_ts"])
def test_reference_substitution_is_detected(field: str) -> None:
    artifact = _artifact()
    captured = _append(
        {
            "event_type": "canonical_decision_link",
            "audit_schema_version": "canonical_decision_trust_link/v1",
            "request_id": artifact.request_id,
            "pipeline_phase": "post_persistence_drift_verified",
            "canonical_decision_ref": build_canonical_decision_reference(
                artifact
            ).model_dump(mode="json"),
        }
    )
    receipt = record_canonical_decision_trust_link(
        artifact, append_trust_log_fn=_append
    )
    captured["canonical_decision_ref"][field] = "0" * 64

    assert not verify_canonical_decision_trust_entry(artifact, receipt, captured).ok


def test_request_substitution_refuses_receipt() -> None:
    artifact = _artifact()

    def substitute(event):
        return _append({**event, "request_id": "substituted"})

    with pytest.raises(CanonicalDecisionTrustLinkError) as exc:
        record_canonical_decision_trust_link(artifact, append_trust_log_fn=substitute)
    assert exc.value.reason_code is CanonicalDecisionTrustLinkReason.REQUEST_ID_MISMATCH


def test_receipt_hash_substitution_is_detected() -> None:
    artifact = _artifact()
    event = {
        "event_type": "canonical_decision_link",
        "audit_schema_version": "canonical_decision_trust_link/v1",
        "request_id": artifact.request_id,
        "pipeline_phase": "post_persistence_drift_verified",
        "canonical_decision_ref": build_canonical_decision_reference(
            artifact
        ).model_dump(mode="json"),
    }
    entry = _append(event)
    receipt = record_canonical_decision_trust_link(
        artifact, append_trust_log_fn=_append
    )
    changed = receipt.model_copy(update={"trust_log_entry_sha256": "b" * 64})
    assert not verify_canonical_decision_trust_entry(artifact, changed, entry).ok


def test_redaction_change_refuses_receipt() -> None:
    artifact = _artifact()

    def redact(event):
        entry = _append(event)
        entry["canonical_decision_ref"]["request_id"] = "[REDACTED]"
        return entry

    with pytest.raises(CanonicalDecisionTrustLinkError) as exc:
        record_canonical_decision_trust_link(artifact, append_trust_log_fn=redact)
    assert (
        exc.value.reason_code
        is CanonicalDecisionTrustLinkReason.TRUSTLOG_REFERENCE_MISMATCH
    )
