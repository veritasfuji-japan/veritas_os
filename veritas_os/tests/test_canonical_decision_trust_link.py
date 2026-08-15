"""Canonical Decision Artifact to TrustLog exact-link tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from veritas_os.audit import trustlog_signed
from veritas_os.api.schemas import DecideResponse
from veritas_os.audit.canonical_decision_trust_link import (
    CanonicalDecisionTrustReceipt,
    CanonicalDecisionTrustLinkError,
    CanonicalDecisionTrustLinkReason,
    build_canonical_decision_reference,
    record_canonical_decision_trust_link,
    verify_canonical_decision_trust_entry,
)
from veritas_os.governance.canonical_decision_artifact import (
    build_canonical_decision_artifact,
)
from veritas_os.audit.trustlog_verify import verify_full_ledger, verify_trustlogs
from veritas_os.logging import paths as log_paths
from veritas_os.logging import trust_log
from veritas_os.logging.encryption import decrypt, encrypt, generate_key

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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("format_version", "invalid"),
        ("ledger", "invalid"),
        ("event_type", "invalid"),
    ],
)
def test_invalid_copied_receipt_model_is_revalidated(
    field: str,
    value: str,
) -> None:
    """Typed model copies cannot bypass receipt constant validation."""
    artifact = _artifact()
    receipt = record_canonical_decision_trust_link(
        artifact, append_trust_log_fn=_append
    )
    invalid_model = receipt.model_copy(update={field: value})
    entry = _append(
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

    result = verify_canonical_decision_trust_entry(artifact, invalid_model, entry)

    assert result.ok is False
    assert result.reason_codes == ("TRUSTLOG_RECEIPT_INVALID",)


def test_constructed_receipt_model_is_revalidated() -> None:
    """A model_construct instance is normalized and validated from raw JSON."""
    artifact = _artifact()
    valid = record_canonical_decision_trust_link(
        artifact, append_trust_log_fn=_append
    )
    invalid_model = CanonicalDecisionTrustReceipt.model_construct(
        **{
            **valid.model_dump(mode="json"),
            "format_version": "invalid",
        }
    )
    entry = _append(
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

    result = verify_canonical_decision_trust_entry(artifact, invalid_model, entry)

    assert result.ok is False
    assert result.reason_codes == ("TRUSTLOG_RECEIPT_INVALID",)


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


def _isolate_real_trustlog(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirect the production full and witness ledgers into a temporary root."""
    log_dir = tmp_path / "logs"
    full_path = log_dir / "trust_log.jsonl"
    aggregate_path = log_dir / "trust_log.json"
    witness_path = log_dir / "trustlog.jsonl"
    key_dir = log_dir / "keys"
    monkeypatch.setenv("VERITAS_ENCRYPTION_KEY", generate_key())
    monkeypatch.setenv("VERITAS_TRUSTLOG_SIGNER_BACKEND", "file")
    monkeypatch.setattr(log_paths, "LOG_DIR", log_dir)
    monkeypatch.setattr(log_paths, "LOG_JSONL", full_path)
    monkeypatch.setattr(log_paths, "LOG_JSON", aggregate_path)
    monkeypatch.setattr(trust_log, "LOG_DIR", log_dir)
    monkeypatch.setattr(trust_log, "LOG_JSONL", full_path)
    monkeypatch.setattr(trust_log, "LOG_JSON", aggregate_path)
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_JSONL", witness_path)
    monkeypatch.setattr(trustlog_signed, "SIGNED_TRUSTLOG_KEYS", key_dir)
    monkeypatch.setattr(
        trustlog_signed,
        "PRIVATE_KEY_PATH",
        key_dir / "trustlog_ed25519_private.key",
    )
    monkeypatch.setattr(
        trustlog_signed,
        "PUBLIC_KEY_PATH",
        key_dir / "trustlog_ed25519_public.key",
    )
    return full_path, witness_path


def _read_full_rows(path: Path) -> list[dict]:
    return [
        json.loads(decrypt(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _read_witness_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_real_full_ledger_and_signed_witness_linkage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Exercise the encrypted production append and exact signed-row linkage."""
    full_path, witness_path = _isolate_real_trustlog(tmp_path, monkeypatch)
    artifact = _artifact()

    receipt = record_canonical_decision_trust_link(
        artifact,
        append_trust_log_fn=trust_log.append_trust_log,
    )
    full_rows = _read_full_rows(full_path)
    link_row = next(
        row for row in full_rows if row["sha256"] == receipt.trust_log_entry_sha256
    )
    reference = build_canonical_decision_reference(artifact).model_dump(mode="json")
    witness_rows = _read_witness_rows(witness_path)
    locator = "sha256:" + receipt.trust_log_entry_sha256
    witness_row = next(
        row
        for row in witness_rows
        if row.get("artifact_ref", {}).get("artifact_storage_backend")
        == "trustlog_full_ledger"
        and row.get("artifact_ref", {}).get("artifact_locator") == locator
    )

    assert receipt.trust_log_entry_sha256 == link_row["sha256"]
    assert receipt.trust_log_entry_sha256_prev == link_row["sha256_prev"]
    assert receipt.trust_log_created_at == link_row["created_at"]
    assert receipt.trust_log_entry_sha256 != artifact.decision_hash
    assert link_row["canonical_decision_ref"] == reference
    assert witness_row["artifact_ref"]["artifact_locator"] == locator
    full_result = verify_full_ledger(full_path)
    assert full_result["ok"] is True
    assert full_result["chain_ok"] is True
    unified = verify_trustlogs(
        full_log_path=full_path,
        witness_entries=witness_rows,
        verify_signature_fn=trustlog_signed.verify_signature,
        artifact_search_roots=[full_path.parent],
    )
    assert unified["signature_ok"] is True
    assert unified["linkage_ok"] is True

    link_row["canonical_decision_ref"]["decision_hash"] = "0" * 64
    full_path.write_text(
        "\n".join(encrypt(json.dumps(row)) for row in full_rows) + "\n",
        encoding="utf-8",
    )
    tampered = verify_trustlogs(
        full_log_path=full_path,
        witness_entries=witness_rows,
        verify_signature_fn=trustlog_signed.verify_signature,
        artifact_search_roots=[full_path.parent],
    )
    assert tampered["ok"] is False
    assert tampered["full_ledger"]["chain_ok"] is False
    assert tampered["witness_ledger"]["linkage_ok"] is False
