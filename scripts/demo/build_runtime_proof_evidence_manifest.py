#!/usr/bin/env python3
"""Build the deterministic SHA-256 manifest for Runtime Proof Evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

MANIFEST_NAME = "runtime-proof-evidence-manifest.json"
ARTIFACT_NAME = "veritas-runtime-proof-evidence"


def canonical_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON used by the aggregate hash procedure."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def file_role(path: str) -> str:
    """Return a stable reviewer-facing role for a bundled relative path."""
    if path.startswith("decision-pipeline/"):
        return "decision_pipeline_proof"
    if path.startswith("external-bind/"):
        return "external_bind_proof"
    return {"verification-report.json": "combined_verification", "ci-context.json": "ci_provenance", "reviewer-summary.md": "reviewer_summary"}.get(path, "supporting_evidence")


def build_manifest(root: Path, commit_sha: str) -> dict[str, Any]:
    """Hash every regular bundled file except the self-referential manifest."""
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != MANIFEST_NAME):
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        files.append({"path": relative, "role": file_role(relative), "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content)})
    manifest: dict[str, Any] = {
        "format_version": 1,
        "manifest_id": "veritas-runtime-proof-evidence-v1",
        "artifact_name": ARTIFACT_NAME,
        "commit_sha": commit_sha,
        "local_ci_proof_only": True,
        "proofs_independent": True,
        "decision_to_bind_connection_claimed": False,
        "hash_algorithm": "SHA-256",
        "manifest_hash_procedure": "SHA-256 of canonical JSON for this object with manifest_hash omitted",
        "files": files,
    }
    manifest["manifest_hash"] = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    return manifest


def main() -> int:
    """Write a manifest for a bundle directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--commit-sha", required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.bundle, args.commit_sha)
    (args.bundle / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
