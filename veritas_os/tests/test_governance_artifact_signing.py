"""Tests for governance artifact signing enforcement and identity threading.

Covers:
- GovernanceIdentity model and serialization
- GovernanceChangeRecord model and provenance fields
- Digest computation determinism
- Posture-aware signature enforcement (accept/reject by posture)
- Decision artifacts record governance identity
- Governance history captures digest transitions
- Governed rollback with audit trail
- Runtime adapter posture-aware bundle loading
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# GovernanceIdentity model tests
# ---------------------------------------------------------------------------


class TestGovernanceIdentity:
    """Test GovernanceIdentity data model."""

    def test_default_values(self):
        from veritas_os.policy.governance_identity import GovernanceIdentity

        gi = GovernanceIdentity()
        assert gi.policy_version == ""
        assert gi.digest == ""
        assert gi.signature_verified is False
        assert gi.signer_id == ""
        assert gi.verified_at == ""

    def test_to_dict_roundtrip(self):
        from veritas_os.policy.governance_identity import GovernanceIdentity

        gi = GovernanceIdentity(
            policy_version="governance_v1",
            digest="abc123",
            signature_verified=True,
            signer_id="key-001",
            verified_at="2026-01-01T00:00:00Z",
        )
        d = gi.to_dict()
        assert d["policy_version"] == "governance_v1"
        assert d["digest"] == "abc123"
        assert d["signature_verified"] is True
        assert d["signer_id"] == "key-001"
        assert d["verified_at"] == "2026-01-01T00:00:00Z"
        # All keys present
        assert set(d.keys()) == {
            "policy_version", "digest", "signature_verified",
            "signer_id", "verified_at",
        }

    def test_frozen_immutable(self):
        from veritas_os.policy.governance_identity import GovernanceIdentity

        gi = GovernanceIdentity(policy_version="v1")
        with pytest.raises(AttributeError):
            gi.policy_version = "v2"  # type: ignore[misc]


class TestGovernanceChangeRecord:
    """Test GovernanceChangeRecord data model."""

    def test_default_values(self):
        from veritas_os.policy.governance_identity import GovernanceChangeRecord

        rec = GovernanceChangeRecord()
        assert rec.event_type == "update"
        assert rec.approvers == []
        assert rec.signature_status == "unsigned"

    def test_to_dict_contains_provenance(self):
        from veritas_os.policy.governance_identity import GovernanceChangeRecord

        rec = GovernanceChangeRecord(
            changed_at="2026-01-01T00:00:00Z",
            proposer="alice",
            approvers=["bob", "carol"],
            previous_digest="aaa",
            new_digest="bbb",
            previous_version="v1",
            new_version="v2",
            event_type="rollback",
            signature_status="signed-ed25519",
        )
        d = rec.to_dict()
        assert d["proposer"] == "alice"
        assert d["approvers"] == ["bob", "carol"]
        assert d["previous_digest"] == "aaa"
        assert d["new_digest"] == "bbb"
        assert d["event_type"] == "rollback"


# ---------------------------------------------------------------------------
# Digest computation tests
# ---------------------------------------------------------------------------


class TestComputeGovernanceDigest:
    """Test deterministic digest computation."""

    def test_deterministic(self):
        from veritas_os.policy.governance_identity import compute_governance_digest

        policy = {"version": "v1", "fuji_rules": {"pii_check": True}}
        d1 = compute_governance_digest(policy)
        d2 = compute_governance_digest(policy)
        assert d1 == d2
        assert len(d1) == 64  # SHA-256 hex

    def test_different_policies_different_digests(self):
        from veritas_os.policy.governance_identity import compute_governance_digest

        p1 = {"version": "v1"}
        p2 = {"version": "v2"}
        assert compute_governance_digest(p1) != compute_governance_digest(p2)

    def test_key_order_independent(self):
        from veritas_os.policy.governance_identity import compute_governance_digest

        p1 = {"a": 1, "b": 2}
        p2 = {"b": 2, "a": 1}
        assert compute_governance_digest(p1) == compute_governance_digest(p2)


# ---------------------------------------------------------------------------
# build_governance_identity tests
# ---------------------------------------------------------------------------


class TestBuildGovernanceIdentity:
    """Test building GovernanceIdentity from policy data."""

    def test_basic_build(self):
        from veritas_os.policy.governance_identity import (
            build_governance_identity,
            compute_governance_digest,
        )

        policy = {"version": "governance_v1", "fuji_rules": {}}
        gi = build_governance_identity(policy)
        assert gi.policy_version == "governance_v1"
        assert gi.digest == compute_governance_digest(policy)
        assert gi.signature_verified is False
        assert gi.verified_at  # non-empty timestamp

    def test_with_signature(self):
        from veritas_os.policy.governance_identity import build_governance_identity

        policy = {"version": "v1"}
        gi = build_governance_identity(
            policy,
            signature_verified=True,
            signer_id="key-fingerprint-abc",
        )
        assert gi.signature_verified is True
        assert gi.signer_id == "key-fingerprint-abc"


# ---------------------------------------------------------------------------
# Posture-aware signature enforcement
# ---------------------------------------------------------------------------


class TestRequireSignedGovernance:
    """Test posture-aware governance artifact signing enforcement."""

    def test_signed_accepted_in_strict(self):
        from veritas_os.policy.governance_identity import require_signed_governance

        # No exception for signed artifacts even in strict posture
        require_signed_governance(
            {"version": "v1"},
            posture_is_strict=True,
            signature_verified=True,
        )

    def test_signed_accepted_in_dev(self):
        from veritas_os.policy.governance_identity import require_signed_governance

        require_signed_governance(
            {"version": "v1"},
            posture_is_strict=False,
            signature_verified=True,
        )

    def test_unsigned_rejected_in_strict(self):
        from veritas_os.policy.governance_identity import require_signed_governance

        with pytest.raises(ValueError, match="unsigned"):
            require_signed_governance(
                {"version": "v1"},
                posture_is_strict=True,
                signature_verified=False,
            )

    def test_unsigned_accepted_in_dev_with_warning(self, caplog):
        from veritas_os.policy.governance_identity import require_signed_governance

        import logging
        with caplog.at_level(logging.WARNING):
            require_signed_governance(
                {"version": "v1"},
                posture_is_strict=False,
                signature_verified=False,
            )
        assert "unsigned" in caplog.text.lower()

    def test_invalid_signature_rejected_in_strict(self):
        from veritas_os.policy.governance_identity import require_signed_governance

        with pytest.raises(ValueError, match="invalid signature"):
            require_signed_governance(
                {"version": "v1"},
                posture_is_strict=True,
                signature_verified=False,
            )


# ---------------------------------------------------------------------------
# Decision artifact governance identity threading
# ---------------------------------------------------------------------------


class TestDecideResponseGovernanceIdentity:
    """Test that DecideResponse schema includes governance_identity field."""

    def test_field_exists_and_defaults_none(self):
        from veritas_os.api.schemas import DecideResponse

        resp = DecideResponse()
        assert resp.governance_identity is None

    def test_field_accepts_dict(self):
        from veritas_os.api.schemas import DecideResponse

        gi_dict = {
            "policy_version": "v1",
            "digest": "abc123",
            "signature_verified": True,
            "signer_id": "key-001",
            "verified_at": "2026-01-01T00:00:00Z",
        }
        resp = DecideResponse(governance_identity=gi_dict)
        assert resp.governance_identity == gi_dict

    def test_model_validate_preserves_governance_identity(self):
        from veritas_os.api.schemas import DecideResponse

        gi_dict = {"policy_version": "v1", "digest": "abc123"}
        data = {"governance_identity": gi_dict}
        resp = DecideResponse.model_validate(data)
        assert resp.governance_identity is not None
        assert resp.governance_identity["policy_version"] == "v1"

    def test_model_dump_includes_governance_identity(self):
        from veritas_os.api.schemas import DecideResponse

        gi_dict = {"policy_version": "v1", "digest": "abc123"}
        resp = DecideResponse(governance_identity=gi_dict)
        dumped = resp.model_dump()
        assert "governance_identity" in dumped
        assert dumped["governance_identity"]["policy_version"] == "v1"


# ---------------------------------------------------------------------------
# Pipeline context governance identity
# ---------------------------------------------------------------------------


class TestPipelineContextGovernanceIdentity:
    """Test governance_identity field on PipelineContext."""

    def test_default_none(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        assert ctx.governance_identity is None

    def test_can_set(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext

        ctx = PipelineContext()
        ctx.governance_identity = {"policy_version": "v1", "digest": "abc"}
        assert ctx.governance_identity["policy_version"] == "v1"


# ---------------------------------------------------------------------------
# Pipeline response assembly includes governance identity
# ---------------------------------------------------------------------------


class TestResponseAssemblyGovernanceIdentity:
    """Test that assemble_response threads governance_identity into output."""

    def test_governance_identity_in_assembled_response(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = PipelineContext()
        ctx.governance_identity = {"policy_version": "v1", "digest": "abc"}
        ctx.response_extras = {"metrics": {"stage_latency": {}}}

        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {},
            plan={"steps": []},
        )
        assert "governance_identity" in res
        assert res["governance_identity"]["policy_version"] == "v1"

    def test_governance_identity_none_when_not_set(self):
        from veritas_os.core.pipeline.pipeline_types import PipelineContext
        from veritas_os.core.pipeline.pipeline_response import assemble_response

        ctx = PipelineContext()
        ctx.response_extras = {"metrics": {"stage_latency": {}}}

        res = assemble_response(
            ctx,
            load_persona_fn=lambda: {},
            plan={"steps": []},
        )
        assert res.get("governance_identity") is None


# ---------------------------------------------------------------------------
# Enhanced governance history (digest transitions)
# ---------------------------------------------------------------------------


class TestGovernanceHistoryDigests:
    """Test that governance history captures digest transitions."""

    def test_history_includes_digests(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov
        from veritas_os.policy.governance_identity import compute_governance_digest

        # Use temp paths to avoid polluting real files
        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)

        # Create initial policy
        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        # Update policy
        gov.update_policy({"version": "governance_v2", "updated_by": "alice"})

        # Read history
        records = gov.get_policy_history(limit=1)
        assert len(records) == 1
        rec = records[0]

        # Verify digest fields exist
        assert "previous_digest" in rec
        assert "new_digest" in rec
        assert rec["previous_digest"] != ""
        assert rec["new_digest"] != ""
        assert rec["previous_digest"] != rec["new_digest"]

    def test_history_includes_proposer_and_approvers(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        gov.update_policy({
            "version": "governance_v2",
            "updated_by": "alice",
            "approvals": [
                {"reviewer": "bob", "signature": "sig1"},
                {"reviewer": "carol", "signature": "sig2"},
            ],
        })

        records = gov.get_policy_history(limit=1)
        assert len(records) == 1
        rec = records[0]
        assert rec["proposer"] == "alice"
        assert "bob" in rec["approvers"]
        assert "carol" in rec["approvers"]

    def test_history_event_type_defaults_to_update(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        gov.update_policy({"version": "governance_v2"})

        records = gov.get_policy_history(limit=1)
        assert records[0]["event_type"] == "update"


# ---------------------------------------------------------------------------
# Governed rollback tests
# ---------------------------------------------------------------------------


class TestGovernedRollback:
    """Test that governance rollback is governed with audit trail."""

    def test_rollback_requires_four_eyes(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "1")

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        with pytest.raises(PermissionError, match="two approvals"):
            gov.rollback_policy(
                deepcopy(initial),
                rolled_back_by="alice",
                approvals=[],  # insufficient
            )

    def test_rollback_succeeds_with_approvals(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "1")

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        target = deepcopy(initial)
        target["version"] = "governance_v_rollback"
        result = gov.rollback_policy(
            target,
            rolled_back_by="dave",
            approvals=[
                {"reviewer": "alice", "signature": "sig-a"},
                {"reviewer": "bob", "signature": "sig-b"},
            ],
            reason="critical regression",
        )
        assert result["version"] == "governance_v_rollback"
        assert result["updated_by"] == "dave"

    def test_rollback_recorded_in_history(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        history_path = tmp_path / "governance_history.jsonl"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setattr(gov, "_POLICY_HISTORY_PATH", history_path)
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        target = deepcopy(initial)
        target["version"] = "governance_v_rollback"
        gov.rollback_policy(
            target,
            rolled_back_by="admin",
        )

        records = gov.get_policy_history(limit=1)
        assert len(records) == 1
        assert records[0]["event_type"] == "rollback"
        assert "previous_digest" in records[0]
        assert "new_digest" in records[0]

    def test_rollback_rejects_invalid_policy(self, tmp_path, monkeypatch):
        from veritas_os.api import governance as gov

        policy_path = tmp_path / "governance.json"
        monkeypatch.setattr(gov, "_DEFAULT_POLICY_PATH", policy_path)
        monkeypatch.setenv("VERITAS_GOVERNANCE_REQUIRE_FOUR_EYES", "0")

        initial = gov.GovernancePolicy().model_dump()
        gov._save(initial)

        with pytest.raises(TypeError, match="target_policy must be a dict"):
            gov.rollback_policy("not_a_dict")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Runtime adapter posture-aware bundle loading
# ---------------------------------------------------------------------------


class TestRuntimeAdapterPostureAwareness:
    """Test that runtime adapter enforces Ed25519 in strict posture."""

    def _make_sha256_bundle(self, bundle_dir: Path) -> None:
        """Create a minimal bundle with SHA-256 signing (no Ed25519)."""
        (bundle_dir / "compiled").mkdir(parents=True, exist_ok=True)
        canonical_ir = {
            "policy_id": "test-policy",
            "version": "1.0",
            "title": "Test",
            "description": "Test policy",
            "scope": {"domains": [], "routes": [], "actors": []},
            "conditions": [],
            "constraints": [],
            "requirements": {"min_evidence": 0, "min_approvals": 0, "reviewer_count": 0},
            "outcome": {"decision": "allow", "reason": "test"},
            "obligations": [],
            "test_vectors": [],
            "metadata": {},
            "source_refs": [],
        }
        manifest = {
            "schema_version": "0.1",
            "policy_id": "test-policy",
            "version": "1.0",
            "semantic_hash": "abc123",
            "compiler_version": "0.1.0",
            "compiled_at": "2026-01-01T00:00:00Z",
            "signing": {"algorithm": "sha256", "status": "signed-local"},
        }
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        (bundle_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")
        digest = hashlib.sha256(manifest_json.encode()).hexdigest()
        (bundle_dir / "manifest.sig").write_text(digest, encoding="utf-8")
        ir_json = json.dumps(canonical_ir, sort_keys=True, separators=(",", ":"))
        (bundle_dir / "compiled" / "canonical_ir.json").write_text(ir_json, encoding="utf-8")

    def test_sha256_bundle_rejected_in_strict_posture(self, tmp_path, monkeypatch):
        from veritas_os.policy.runtime_adapter import load_runtime_bundle
        from veritas_os.core.posture import PostureDefaults, PostureLevel

        bundle_dir = tmp_path / "bundle"
        self._make_sha256_bundle(bundle_dir)

        mock_posture = PostureDefaults(posture=PostureLevel.PROD)
        monkeypatch.setattr(
            "veritas_os.core.posture.get_active_posture",
            lambda: mock_posture,
        )

        with pytest.raises(ValueError, match="secure/prod posture"):
            load_runtime_bundle(bundle_dir)

    def test_sha256_bundle_accepted_in_dev_posture(self, tmp_path, monkeypatch):
        from veritas_os.policy.runtime_adapter import load_runtime_bundle
        from veritas_os.core.posture import PostureDefaults, PostureLevel

        bundle_dir = tmp_path / "bundle"
        self._make_sha256_bundle(bundle_dir)

        mock_posture = PostureDefaults(posture=PostureLevel.DEV)
        monkeypatch.setattr(
            "veritas_os.core.posture.get_active_posture",
            lambda: mock_posture,
        )

        bundle = load_runtime_bundle(bundle_dir)
        assert bundle.policy_id == "test-policy"

    def test_ed25519_bundle_accepted_in_strict_posture(self, tmp_path, monkeypatch):
        from veritas_os.policy.signing import generate_keypair, sign_manifest
        from veritas_os.policy.runtime_adapter import load_runtime_bundle
        from veritas_os.core.posture import PostureDefaults, PostureLevel

        priv_pem, pub_pem = generate_keypair()
        bundle_dir = tmp_path / "bundle"
        (bundle_dir / "compiled").mkdir(parents=True, exist_ok=True)

        canonical_ir = {
            "policy_id": "test-policy-signed",
            "version": "2.0",
            "title": "Signed Test",
            "description": "Test policy with Ed25519 signature",
            "scope": {"domains": [], "routes": [], "actors": []},
            "conditions": [],
            "constraints": [],
            "requirements": {"min_evidence": 0, "min_approvals": 0, "reviewer_count": 0},
            "outcome": {"decision": "allow", "reason": "test"},
            "obligations": [],
            "test_vectors": [],
            "metadata": {},
            "source_refs": [],
        }
        manifest = {
            "schema_version": "0.1",
            "policy_id": "test-policy-signed",
            "version": "2.0",
            "semantic_hash": "def456",
            "compiler_version": "0.1.0",
            "compiled_at": "2026-01-01T00:00:00Z",
            "signing": {"algorithm": "ed25519", "status": "signed-ed25519"},
        }
        manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        (bundle_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")
        sig = sign_manifest(manifest_json.encode("utf-8"), priv_pem)
        (bundle_dir / "manifest.sig").write_text(sig, encoding="utf-8")
        ir_json = json.dumps(canonical_ir, sort_keys=True, separators=(",", ":"))
        (bundle_dir / "compiled" / "canonical_ir.json").write_text(ir_json, encoding="utf-8")

        mock_posture = PostureDefaults(posture=PostureLevel.PROD)
        monkeypatch.setattr(
            "veritas_os.core.posture.get_active_posture",
            lambda: mock_posture,
        )

        bundle = load_runtime_bundle(bundle_dir, public_key_pem=pub_pem)
        assert bundle.policy_id == "test-policy-signed"
        assert bundle.version == "2.0"


# ---------------------------------------------------------------------------
# Missing signature behavior differs by posture
# ---------------------------------------------------------------------------


class TestMissingSignatureBehavior:
    """Test that missing signature is handled differently by posture."""

    def test_missing_sig_file_always_fails(self, tmp_path):
        from veritas_os.policy.runtime_adapter import verify_manifest_signature

        bundle_dir = tmp_path / "bundle"
        bundle_dir.mkdir()
        (bundle_dir / "manifest.json").write_text("{}", encoding="utf-8")
        # No manifest.sig
        assert verify_manifest_signature(bundle_dir) is False

    def test_missing_sig_rejected_in_strict_posture(self, tmp_path, monkeypatch):
        from veritas_os.policy.runtime_adapter import load_runtime_bundle
        from veritas_os.core.posture import PostureDefaults, PostureLevel

        bundle_dir = tmp_path / "bundle"
        (bundle_dir / "compiled").mkdir(parents=True, exist_ok=True)
        (bundle_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "policy_id": "missing-sig-policy",
                    "version": "1.0",
                    "semantic_hash": "abc123",
                    "compiler_version": "0.1.0",
                    "compiled_at": "2026-01-01T00:00:00Z",
                    "signing": {"algorithm": "sha256", "status": "unsigned"},
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        (bundle_dir / "compiled" / "canonical_ir.json").write_text(
            json.dumps(
                {
                    "policy_id": "missing-sig-policy",
                    "version": "1.0",
                    "title": "Missing Sig",
                    "description": "Test",
                    "scope": {"domains": [], "routes": [], "actors": []},
                    "conditions": [],
                    "constraints": [],
                    "requirements": {
                        "min_evidence": 0,
                        "min_approvals": 0,
                        "reviewer_count": 0,
                    },
                    "outcome": {"decision": "allow", "reason": "test"},
                    "obligations": [],
                    "test_vectors": [],
                    "metadata": {},
                    "source_refs": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "veritas_os.core.posture.get_active_posture",
            lambda: PostureDefaults(posture=PostureLevel.PROD),
        )

        with pytest.raises(ValueError, match="missing manifest.sig"):
            load_runtime_bundle(bundle_dir)

    def test_missing_sig_accepted_in_dev_posture(self, tmp_path, monkeypatch):
        from veritas_os.policy.runtime_adapter import load_runtime_bundle
        from veritas_os.core.posture import PostureDefaults, PostureLevel

        bundle_dir = tmp_path / "bundle"
        (bundle_dir / "compiled").mkdir(parents=True, exist_ok=True)
        (bundle_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "0.1",
                    "policy_id": "missing-sig-policy-dev",
                    "version": "1.1",
                    "semantic_hash": "def456",
                    "compiler_version": "0.1.0",
                    "compiled_at": "2026-01-01T00:00:00Z",
                    "signing": {"algorithm": "sha256", "status": "unsigned"},
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        (bundle_dir / "compiled" / "canonical_ir.json").write_text(
            json.dumps(
                {
                    "policy_id": "missing-sig-policy-dev",
                    "version": "1.1",
                    "title": "Missing Sig Dev",
                    "description": "Test",
                    "scope": {"domains": [], "routes": [], "actors": []},
                    "conditions": [],
                    "constraints": [],
                    "requirements": {
                        "min_evidence": 0,
                        "min_approvals": 0,
                        "reviewer_count": 0,
                    },
                    "outcome": {"decision": "allow", "reason": "test"},
                    "obligations": [],
                    "test_vectors": [],
                    "metadata": {},
                    "source_refs": [],
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "veritas_os.core.posture.get_active_posture",
            lambda: PostureDefaults(posture=PostureLevel.DEV),
        )

        bundle = load_runtime_bundle(bundle_dir)
        assert bundle.policy_id == "missing-sig-policy-dev"

    def test_unsigned_governance_warns_in_dev(self, caplog):
        from veritas_os.policy.governance_identity import require_signed_governance

        import logging
        with caplog.at_level(logging.WARNING):
            require_signed_governance(
                {"version": "v1"},
                posture_is_strict=False,
                signature_verified=False,
            )
        assert "unsigned" in caplog.text.lower()
        assert "would be rejected" in caplog.text.lower()

    def test_unsigned_governance_errors_in_prod(self):
        from veritas_os.policy.governance_identity import require_signed_governance

        with pytest.raises(ValueError, match="secure/prod"):
            require_signed_governance(
                {"version": "v1"},
                posture_is_strict=True,
                signature_verified=False,
            )


def test_compiled_policy_bridge_sets_governance_identity(monkeypatch):
    from veritas_os.core.pipeline.pipeline_policy import (
        _apply_compiled_policy_runtime_bridge,
    )
    from veritas_os.core.pipeline.pipeline_types import PipelineContext
    from veritas_os.policy.runtime_adapter import RuntimePolicy, RuntimePolicyBundle

    runtime_bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id="policy.bridge",
        version="governance_v9",
        semantic_hash="abcde12345",
        compiler_version="0.1.0",
        compiled_at="2026-01-01T00:00:00Z",
        runtime_policies=[
            RuntimePolicy(
                policy_id="policy.bridge",
                version="governance_v9",
                title="Bridge",
                description="Bridge test",
                effective_date=None,
                scope={"domains": [], "routes": [], "actors": []},
                conditions=[],
                constraints=[],
                requirements={},
                outcome={"decision": "allow", "reason": "ok"},
                obligations=[],
                test_vectors=[],
                metadata={},
                source_refs=[],
            )
        ],
        manifest={
            "signing": {"algorithm": "ed25519", "status": "signed-ed25519", "key_id": "ops-key-1"}
        },
    )
    monkeypatch.setattr(
        "veritas_os.core.pipeline.pipeline_policy.load_runtime_bundle",
        lambda *_args, **_kwargs: runtime_bundle,
    )
    monkeypatch.setattr(
        "veritas_os.core.pipeline.pipeline_policy.evaluate_runtime_policies",
        lambda *_args, **_kwargs: type("R", (), {"to_dict": lambda self: {"final_outcome": "allow"}})(),
    )

    ctx = PipelineContext(
        body={},
        query="q",
        user_id="u",
        request_id="r",
        fast_mode=False,
        replay_mode=False,
        mock_external_apis=False,
        seed=0,
        min_ev=1,
        started_at=0.0,
        is_veritas_query=False,
        context={"compiled_policy_bundle_dir": "/mock/bundle", "policy_runtime_enforce": True},
        response_extras={},
        plan={},
    )

    _apply_compiled_policy_runtime_bridge(ctx)
    assert ctx.governance_identity is not None
    assert ctx.governance_identity["policy_version"] == "governance_v9"
    assert ctx.governance_identity["digest"] == "abcde12345"
    assert ctx.governance_identity["signature_verified"] is True
    assert ctx.governance_identity["signer_id"] == "ops-key-1"
