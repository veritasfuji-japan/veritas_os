"""Unit tests for strict local WAT admissibility verifier."""

from __future__ import annotations

from pathlib import Path

from veritas_os.security.signing import FileEd25519Signer
from veritas_os.security.wat_token import WAT_VERSION_V1, build_wat_claims, sign_wat
from veritas_os.security.wat_verifier import DriftVector, score_drift, validate_local


def _make_signer(tmp_path: Path) -> FileEd25519Signer:
    signer = FileEd25519Signer(
        private_key_path=tmp_path / "keys" / "wat-private.key",
        public_key_path=tmp_path / "keys" / "wat-public.key",
    )
    signer.ensure_key_material()
    return signer


def _signed_wat(tmp_path: Path) -> tuple[FileEd25519Signer, dict[str, object]]:
    signer = _make_signer(tmp_path)
    claims = build_wat_claims(
        version=WAT_VERSION_V1,
        psid_full="psid-full-001",
        action_payload={"action": "allow", "resource": "r-1"},
        observable_refs=[{"obs": "A"}],
        issuance_ts=1_712_000_000,
        expiry_ts=1_712_000_600,
        session_id="session-1",
        nonce="nonce-1",
        signer_metadata={"source": "unit-test"},
    )
    return signer, sign_wat(claims, signer)


def _signed_wat_with_claim_overrides(
    tmp_path: Path,
    *,
    remove_keys: set[str] | None = None,
    updates: dict[str, object] | None = None,
) -> tuple[FileEd25519Signer, dict[str, object]]:
    """Build a signed WAT with controlled claim mutations for verifier tests."""
    signer, signed_wat = _signed_wat(tmp_path)
    claims = dict(signed_wat["claims"])
    for key in remove_keys or set():
        claims.pop(key, None)
    if updates:
        claims.update(updates)
    return signer, sign_wat(claims, signer)


def test_validate_local_valid_path(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "valid"
    assert result["admissibility_state"] == "admissible"


def test_validate_local_signature_invalid(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    signed_wat["signature"] = "invalid-signature"
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "signature_invalid"


def test_validate_local_psid_mismatch(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="wrong-psid",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["failure_type"] == "psid_full_mismatch"


def test_validate_local_action_digest_mismatch(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local="wrong-action-digest",
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["failure_type"] == "action_digest_mismatch"


def test_validate_local_observable_digest_mismatch(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local="wrong-observable-digest",
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["failure_type"] == "observable_digest_mismatch"


def test_validate_local_expired_token_returns_stale(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_601,
    )
    assert result["validation_status"] == "stale"


def test_validate_local_replay_detected_by_binding_reuse(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    replay_cache: set[str] = set()
    first = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
        replay_cache=replay_cache,
    )
    second = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
        replay_cache=replay_cache,
    )
    assert first["validation_status"] == "valid"
    assert second["failure_type"] == "replay_detected"


def test_validate_local_replay_cache_hit_fails_when_required_true(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    claims = signed_wat["claims"]
    replay_cache: set[str] = set()
    _ = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
        replay_cache=replay_cache,
    )
    replay = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
        replay_cache=replay_cache,
    )
    assert replay["validation_status"] == "invalid"
    assert replay["failure_type"] == "replay_detected"


def test_validate_local_required_true_fails_on_missing_nonce(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat_with_claim_overrides(tmp_path, remove_keys={"nonce"})
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "replay_binding_incomplete"
    assert "replay_binding_incomplete" in result["operator_message"]


def test_validate_local_required_true_fails_on_missing_session(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat_with_claim_overrides(tmp_path, remove_keys={"session_id"})
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "replay_binding_incomplete"


def test_validate_local_required_true_fails_on_missing_action_digest(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat_with_claim_overrides(tmp_path, remove_keys={"action_digest"})
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local="",
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce=str(claims["nonce"]),
        session_id=str(claims["session_id"]),
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "replay_binding_incomplete"


def test_validate_local_required_true_fails_on_binding_mismatch(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="nonce-mismatch",
        session_id="session-1",
        revocation_state="active",
        config={"replay_binding_required": True},
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "replay_binding_incomplete"


def test_validate_local_required_false_keeps_observer_friendly_missing_binding(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat_with_claim_overrides(
        tmp_path,
        remove_keys={"nonce", "session_id"},
    )
    claims = signed_wat["claims"]
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=int(claims["issuance_ts"]),
        expiry_ts_local=int(claims["expiry_ts"]),
        execution_nonce="",
        session_id="",
        revocation_state="active",
        config={"replay_binding_required": False},
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "valid"
    assert result["failure_type"] is None


def test_validate_local_revoked_pending_is_warning_only(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="revoked_pending",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "revoked_pending"
    assert result["admissibility_state"] == "warning_only_shadow"


def test_validate_local_revoked_confirmed_is_hard_fail(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    result = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="revoked_confirmed",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "revoked_confirmed"
    assert result["admissibility_state"] == "non_admissible"


def test_validate_local_partial_requires_timebox(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    expired_timebox = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
        config={
            "allow_partial_validation": True,
            "observer_only_mode": True,
            "warning_only_until": 1_712_000_050,
        },
    )
    active_timebox = validate_local(
        signed_wat=signed_wat,
        psid_full_local="psid-full-001",
        action_digest_local=str(signed_wat["claims"]["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(signed_wat["claims"]["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
        config={
            "allow_partial_validation": True,
            "observer_only_mode": True,
            "warning_only_until": 1_712_000_500,
        },
    )
    assert expired_timebox["admissibility_state"] == "non_admissible"
    assert active_timebox["admissibility_state"] == "warning_only_shadow"


def test_psid_display_does_not_influence_enforcement(tmp_path: Path) -> None:
    signer, signed_wat = _signed_wat(tmp_path)
    claims = dict(signed_wat["claims"])
    claims["psid_display"] = "tampered-display"
    result = validate_local(
        signed_wat={"claims": claims, "signature": signed_wat["signature"]},
        psid_full_local="psid-full-001",
        action_digest_local=str(claims["action_digest"]),
        observable_refs_local=[{"obs": "A"}],
        observable_digest_local=str(claims["observable_digest"]),
        issuance_ts_local=1_712_000_000,
        expiry_ts_local=1_712_000_600,
        execution_nonce="nonce-1",
        session_id="session-1",
        revocation_state="active",
        signer=signer,
        now_ts=1_712_000_100,
    )
    assert result["validation_status"] == "invalid"
    assert result["failure_type"] == "signature_invalid"


def test_drift_score_classification() -> None:
    healthy = score_drift(DriftVector(0.1, 0.0, 0.0, 0.0))
    warning = score_drift(DriftVector(0.0, 0.7, 0.0, 0.0))
    critical = score_drift(DriftVector(1.0, 1.0, 1.0, 1.0))
    assert healthy.classification == "healthy"
    assert warning.classification == "warning"
    assert critical.classification == "critical"


def test_drift_score_custom_weights_affect_classification() -> None:
    """Custom weight map from policy must influence drift classification."""
    drift_vector = DriftVector(0.0, 0.7, 0.0, 0.0)
    baseline = score_drift(drift_vector)
    custom = score_drift(
        drift_vector,
        weights={
            "policy": 0.7,
            "signature": 0.1,
            "observable": 0.1,
            "temporal": 0.1,
        },
    )
    assert baseline.classification == "warning"
    assert custom.classification == "healthy"


def test_drift_score_custom_thresholds_affect_classification() -> None:
    """Custom threshold map from policy must influence drift classification."""
    drift_vector = DriftVector(0.3, 0.0, 0.0, 0.0)
    default_score = score_drift(drift_vector)
    custom_score = score_drift(
        drift_vector,
        thresholds={"healthy": 0.05, "critical": 0.15},
    )
    assert default_score.classification == "healthy"
    assert custom_score.classification == "warning"
