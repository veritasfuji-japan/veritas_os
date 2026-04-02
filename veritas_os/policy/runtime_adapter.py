"""Runtime adapter for compiled policy artifacts.

This module bridges compiled policy artifacts (canonical IR / manifest / bundle)
into runtime-evaluable policy structures used by governance and pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping

from .ir import CanonicalPolicyIR


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
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping json at {path}")
    return data


def verify_manifest_signature(bundle_dir: str | Path) -> bool:
    """Verify ``manifest.sig`` for a compiled bundle."""
    root = Path(bundle_dir)
    manifest_path = root / "manifest.json"
    signature_path = root / "manifest.sig"
    if not manifest_path.exists() or not signature_path.exists():
        return False
    expected = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    observed = signature_path.read_text(encoding="utf-8").strip()
    return expected == observed


def adapt_canonical_ir(canonical_ir: CanonicalPolicyIR) -> RuntimePolicy:
    """Convert canonical policy IR mapping into a runtime-ready policy object."""
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


def load_runtime_bundle(bundle_dir: str | Path) -> RuntimePolicyBundle:
    """Load a compiled bundle directory and adapt it for runtime evaluation."""
    root = Path(bundle_dir)
    if not verify_manifest_signature(root):
        raise ValueError("manifest signature verification failed")
    manifest = _read_json_file(root / "manifest.json")
    canonical_ir = _read_json_file(root / "compiled" / "canonical_ir.json")

    runtime_policy = adapt_canonical_ir(canonical_ir)

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
