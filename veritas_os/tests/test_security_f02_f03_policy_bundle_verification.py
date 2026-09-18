"""Regression tests for security findings F-02 / F-03.

F-02: the signed manifest must bind the exact policy bytes evaluated at runtime.
F-03: Ed25519-declared artifacts must never downgrade to SHA-256 when trusted
verification key material is unavailable, and runtime signature identity must
come from verifier success rather than manifest self-claims.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from veritas_os.core.pipeline import pipeline_policy as pp
from veritas_os.core.pipeline.pipeline_types import PipelineContext
from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.emit import stable_json_dumps
from veritas_os.policy.runtime_adapter import (
    RuntimePolicy,
    RuntimePolicyBundle,
    load_runtime_bundle,
)
from veritas_os.policy.signing import generate_keypair, sign_manifest

EXAMPLES_DIR = Path("policies/examples")


def _rewrite_manifest_and_resign(
    manifest_path: Path,
    *,
    private_key: bytes,
    mutate,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(manifest)
    manifest_bytes = stable_json_dumps(manifest).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    (manifest_path.parent / "manifest.sig").write_text(
        sign_manifest(manifest_bytes, private_key) + "\n",
        encoding="utf-8",
    )
    return manifest


def _refresh_canonical_entry(manifest: dict[str, Any], canonical_path: Path) -> None:
    payload = canonical_path.read_bytes()
    for entry in manifest["bundle_contents"]:
        if entry["path"] == "compiled/canonical_ir.json":
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["size"] = len(payload)
            return
    raise AssertionError("canonical_ir entry missing from manifest")


def test_f02_signed_manifest_rejects_tampered_canonical_body(
    tmp_path: Path,
) -> None:
    private_key, public_key = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-09-18T00:00:00Z",
        signing_key=private_key,
    )

    canonical_path = result.bundle_dir / "compiled" / "canonical_ir.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["outcome"]["decision"] = "allow"
    canonical_path.write_text(stable_json_dumps(canonical), encoding="utf-8")

    with pytest.raises(ValueError, match="content digest mismatch"):
        load_runtime_bundle(result.bundle_dir, public_key_pem=public_key)


def test_f02_recomputes_semantic_hash_from_verified_canonical_bytes(
    tmp_path: Path,
) -> None:
    private_key, public_key = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-09-18T00:01:00Z",
        signing_key=private_key,
    )

    canonical_path = result.bundle_dir / "compiled" / "canonical_ir.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    canonical["outcome"]["decision"] = "allow"
    canonical_path.write_text(stable_json_dumps(canonical), encoding="utf-8")

    def _mutate(manifest: dict[str, Any]) -> None:
        _refresh_canonical_entry(manifest, canonical_path)
        # Intentionally keep the old semantic_hash. Signature and file digest
        # are valid, so the runtime must independently recompute semantics.

    _rewrite_manifest_and_resign(
        result.manifest_path,
        private_key=private_key,
        mutate=_mutate,
    )

    with pytest.raises(ValueError, match="semantic_hash"):
        load_runtime_bundle(result.bundle_dir, public_key_pem=public_key)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("policy_id", "policy.attacker.substitute", "policy_id"),
        ("version", "999.0.0", "version"),
    ],
)
def test_f02_manifest_identity_must_match_verified_canonical_ir(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
) -> None:
    private_key, public_key = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path,
        compiled_at="2026-09-18T00:02:00Z",
        signing_key=private_key,
    )

    _rewrite_manifest_and_resign(
        result.manifest_path,
        private_key=private_key,
        mutate=lambda manifest: manifest.__setitem__(field, replacement),
    )

    with pytest.raises(ValueError, match=message):
        load_runtime_bundle(result.bundle_dir, public_key_pem=public_key)


def test_f03_ed25519_manifest_cannot_downgrade_to_sha256_without_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from veritas_os.core.posture import PostureDefaults, PostureLevel

    private_key, _ = generate_keypair()
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-09-18T00:03:00Z",
        signing_key=private_key,
    )
    manifest_bytes = result.manifest_path.read_bytes()

    # Reproduce the reported downgrade shape: keep algorithm=ed25519 but replace
    # manifest.sig with a plain SHA-256 digest.
    (result.bundle_dir / "manifest.sig").write_text(
        hashlib.sha256(manifest_bytes).hexdigest(),
        encoding="utf-8",
    )
    monkeypatch.delenv("VERITAS_POLICY_VERIFY_KEY", raising=False)
    monkeypatch.delenv("VERITAS_POLICY_REQUIRE_ED25519", raising=False)
    monkeypatch.setattr(
        "veritas_os.core.posture.get_active_posture",
        lambda: PostureDefaults(posture=PostureLevel.PROD),
    )

    with pytest.raises(ValueError, match="trusted public key"):
        load_runtime_bundle(result.bundle_dir)


def test_f03_signature_verified_is_verifier_derived(
    tmp_path: Path,
) -> None:
    private_key, public_key = generate_keypair()
    signed = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path / "signed",
        compiled_at="2026-09-18T00:04:00Z",
        signing_key=private_key,
    )
    signed_bundle = load_runtime_bundle(
        signed.bundle_dir,
        public_key_pem=public_key,
    )

    assert signed_bundle.manifest_integrity_verified is True
    assert signed_bundle.signature_verified is True
    assert signed_bundle.signature_algorithm == "ed25519"
    assert signed_bundle.bundle_contents_verified is True
    assert signed_bundle.signer_id

    legacy = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path / "legacy",
        compiled_at="2026-09-18T00:05:00Z",
    )
    legacy_bundle = load_runtime_bundle(legacy.bundle_dir)

    assert legacy_bundle.manifest_integrity_verified is True
    assert legacy_bundle.signature_verified is False
    assert legacy_bundle.signature_algorithm == "sha256"
    assert legacy_bundle.signer_id == ""


def test_f03_pipeline_does_not_trust_manifest_signature_self_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RuntimePolicy(
        policy_id="policy.self.claim",
        version="1",
        title="Self claim",
        description="Manifest claims Ed25519 without verifier proof.",
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
    bundle = RuntimePolicyBundle(
        schema_version="0.1",
        policy_id=policy.policy_id,
        version=policy.version,
        semantic_hash="a" * 64,
        compiler_version="test",
        compiled_at="2026-09-18T00:06:00Z",
        runtime_policies=[policy],
        manifest={
            "signing": {
                "algorithm": "ed25519",
                "key_id": "caller-claimed-key",
            }
        },
        # Verifier-derived fields intentionally remain false / empty.
    )
    monkeypatch.setattr(
        pp,
        "_resolve_trusted_runtime_bundle_dir",
        lambda: "/trusted/bundle",
    )
    monkeypatch.setattr(pp, "load_runtime_bundle", lambda _path: bundle)
    monkeypatch.setattr(
        pp,
        "evaluate_runtime_policies",
        lambda _bundle, _ctx: SimpleNamespace(
            to_dict=lambda: {"final_outcome": "allow"}
        ),
    )

    ctx = PipelineContext(
        query="q",
        context={"policy_runtime_enforce": True},
    )
    pp._apply_compiled_policy_runtime_bridge(ctx)

    assert ctx.governance_identity is not None
    assert ctx.governance_identity["signature_verified"] is False
    assert ctx.governance_identity["signer_id"] == ""
