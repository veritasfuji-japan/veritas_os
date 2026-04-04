"""Runtime adapter for compiled policy artifacts.

This module bridges compiled policy artifacts (canonical IR / manifest / bundle)
into runtime-evaluable policy structures used by governance and pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .ir import CanonicalPolicyIR
from .signing import verify_manifest_ed25519

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimePolicy:
    """Runtime-ready policy object derived from canonical policy IR."""

    policy_id: str
    version: str
    title: str
    description: str
    effective_date: str | None
    scope: Dict[str, List[str]]
    conditions: List[Dict[str, Any]]
    constraints: List[Dict[str, Any]]
    requirements: Dict[str, Any]
    outcome: Dict[str, str]
    obligations: List[str]
    test_vectors: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    source_refs: List[str]


@dataclass(frozen=True)
class RuntimePolicyBundle:
    """Runtime policy bundle adapted from compiled artifacts."""

    schema_version: str
    policy_id: str
    version: str
    semantic_hash: str
    compiler_version: str
    compiled_at: str
    runtime_policies: List[RuntimePolicy]
    manifest: Dict[str, Any]


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"failed to read policy bundle file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in policy bundle file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping json at {path}, got {type(data).__name__}")
    return data


def verify_manifest_signature(
    bundle_dir: str | Path,
    *,
    public_key_pem: bytes | None = None,
) -> bool:
    """Verify ``manifest.sig`` for a compiled bundle.

    When *public_key_pem* is provided (or the ``VERITAS_POLICY_VERIFY_KEY``
    environment variable points to a PEM file), Ed25519 verification is used.
    Otherwise falls back to legacy SHA-256 integrity check.
    """
    root = Path(bundle_dir)
    manifest_path = root / "manifest.json"
    signature_path = root / "manifest.sig"
    if not manifest_path.exists() or not signature_path.exists():
        return False

    # Resolve public key from argument or env var
    pub_key = public_key_pem
    if pub_key is None:
        key_path_str = os.environ.get("VERITAS_POLICY_VERIFY_KEY")
        if key_path_str:
            key_path = Path(key_path_str)
            if key_path.is_file():
                pub_key = key_path.read_bytes()

    # Read raw bytes once (used for both algorithm detection and verification)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        logger.warning(
            "failed to read manifest for signature verification: %s", exc
        )
        return False

    try:
        sig_text = signature_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        logger.warning(
            "failed to read signature file for verification: %s", exc
        )
        return False

    # Detect signing algorithm from manifest metadata
    try:
        manifest_data = json.loads(manifest_bytes.decode("utf-8"))
        algorithm = (
            manifest_data.get("signing", {}).get("algorithm", "sha256")
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning(
            "failed to parse manifest.json for algorithm detection: %s; "
            "defaulting to sha256 integrity check",
            exc,
        )
        algorithm = "sha256"

    if algorithm == "ed25519" and pub_key is not None:
        return verify_manifest_ed25519(manifest_bytes, sig_text, pub_key)

    if algorithm == "ed25519" and pub_key is None:
        logger.warning(
            "manifest declares ed25519 signing but no public key is available; "
            "falling back to SHA-256 integrity check (authenticity NOT verified)"
        )

    # Fallback: legacy SHA-256 integrity check (constant-time comparison)
    expected = hashlib.sha256(manifest_bytes).hexdigest()
    return hmac.compare_digest(expected, sig_text)


def adapt_canonical_ir(canonical_ir: CanonicalPolicyIR) -> RuntimePolicy:
    """Convert canonical policy IR mapping into a runtime-ready policy object."""
    try:
        return RuntimePolicy(
            policy_id=canonical_ir["policy_id"],
            version=canonical_ir["version"],
            title=canonical_ir["title"],
            description=canonical_ir["description"],
            effective_date=canonical_ir.get("effective_date"),
            scope={
                "domains": list(canonical_ir["scope"]["domains"]),
                "routes": list(canonical_ir["scope"]["routes"]),
                "actors": list(canonical_ir["scope"]["actors"]),
            },
            conditions=[dict(item) for item in canonical_ir["conditions"]],
            constraints=[dict(item) for item in canonical_ir["constraints"]],
            requirements=dict(canonical_ir["requirements"]),
            outcome=dict(canonical_ir["outcome"]),
            obligations=list(canonical_ir["obligations"]),
            test_vectors=[dict(item) for item in canonical_ir["test_vectors"]],
            metadata=dict(canonical_ir.get("metadata", {})),
            source_refs=list(canonical_ir.get("source_refs", [])),
        )
    except KeyError as exc:
        raise ValueError(
            f"canonical IR missing required key {exc}"
        ) from exc


def load_runtime_bundle(
    bundle_dir: str | Path,
    *,
    public_key_pem: bytes | None = None,
) -> RuntimePolicyBundle:
    """Load a compiled bundle directory and adapt it for runtime evaluation.

    Args:
        public_key_pem: Optional Ed25519 public key in PEM format for
            signature verification.  Falls back to SHA-256 integrity check.
    """
    root = Path(bundle_dir)
    if not verify_manifest_signature(root, public_key_pem=public_key_pem):
        raise ValueError("manifest signature verification failed")
    manifest = _read_json_file(root / "manifest.json")
    canonical_ir = _read_json_file(root / "compiled" / "canonical_ir.json")

    runtime_policy = adapt_canonical_ir(canonical_ir)

    logger.info(
        "bundle loaded: policy_id=%s version=%s hash=%s",
        runtime_policy.policy_id,
        runtime_policy.version,
        manifest.get("semantic_hash", ""),
    )

    return RuntimePolicyBundle(
        schema_version=str(manifest.get("schema_version", "0.1")),
        policy_id=runtime_policy.policy_id,
        version=runtime_policy.version,
        semantic_hash=str(manifest.get("semantic_hash", "")),
        compiler_version=str(manifest.get("compiler_version", "")),
        compiled_at=str(manifest.get("compiled_at", "")),
        runtime_policies=[runtime_policy],
        manifest=manifest,
    )


def adapt_compiled_payload(
    *,
    canonical_ir: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> RuntimePolicyBundle:
    """Adapt in-memory compiled payloads (useful for API/pipeline integration)."""
    runtime_policy = adapt_canonical_ir(dict(canonical_ir))
    return RuntimePolicyBundle(
        schema_version=str(manifest.get("schema_version", "0.1")),
        policy_id=runtime_policy.policy_id,
        version=runtime_policy.version,
        semantic_hash=str(manifest.get("semantic_hash", "")),
        compiler_version=str(manifest.get("compiler_version", "")),
        compiled_at=str(manifest.get("compiled_at", "")),
        runtime_policies=[runtime_policy],
        manifest=dict(manifest),
    )
