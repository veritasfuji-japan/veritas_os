"""Manifest builder for compiled policy bundles."""

from __future__ import annotations

from typing import Any, Dict, List

from .ir import CanonicalPolicyIR

MANIFEST_SCHEMA_VERSION = "0.1"


def build_manifest(
    canonical_ir: CanonicalPolicyIR,
    *,
    semantic_hash: str,
    compiler_version: str,
    compiled_at: str,
    source_files: List[str],
    bundle_files: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build manifest metadata for bundle distribution and audit workflows."""
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "policy_id": canonical_ir["policy_id"],
        "version": canonical_ir["version"],
        "semantic_hash": semantic_hash,
        "compiler_version": compiler_version,
        "compiled_at": compiled_at,
        "effective_date": canonical_ir["effective_date"],
        "source_files": sorted(source_files),
        "source_refs": canonical_ir["source_refs"],
        "outcome_summary": {
            "decision": canonical_ir["outcome"]["decision"],
            "reason": canonical_ir["outcome"]["reason"],
            "obligation_count": len(canonical_ir["obligations"]),
            "condition_count": len(canonical_ir["conditions"]),
            "constraint_count": len(canonical_ir["constraints"]),
        },
        "bundle_contents": sorted(bundle_files, key=lambda item: item["path"]),
        "signing": {
            "status": "unsigned",
            "signature_ref": None,
            "key_id": None,
            "extensions": {},
        },
    }
