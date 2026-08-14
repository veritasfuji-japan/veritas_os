#!/usr/bin/env python3
"""Verify a downloaded Runtime Proof Evidence manifest offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.build_runtime_proof_evidence_manifest import (  # noqa: E402
    MANIFEST_NAME,
    canonical_bytes,
)

REQUIRED = {"decision-pipeline/report.json", "external-bind/committed.json", "external-bind/blocked.json", "external-bind/rolled-back.json", "external-bind/manifest.json", "verification-report.json", "ci-context.json", "reviewer-summary.md"}


def verify_manifest(root: Path) -> dict[str, Any]:
    """Fail closed on malformed metadata, unsafe paths, or digest mismatches."""
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load manifest: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("manifest must be an object containing a file list")
    supplied_hash = manifest.get("manifest_hash")
    unhashed = dict(manifest)
    unhashed.pop("manifest_hash", None)
    if supplied_hash != hashlib.sha256(canonical_bytes(unhashed)).hexdigest():
        raise ValueError("aggregate manifest hash mismatch")
    seen: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("malformed file entry")
        relative = entry["path"]
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or relative in seen:
            raise ValueError(f"unsafe or duplicate path: {relative}")
        seen.add(relative)
        path = root.joinpath(*pure.parts)
        if not path.is_file():
            raise ValueError(f"missing bundled file: {relative}")
        content = path.read_bytes()
        if entry.get("size_bytes") != len(content) or entry.get("sha256") != hashlib.sha256(content).hexdigest():
            raise ValueError(f"file integrity mismatch: {relative}")
        if path.suffix == ".json":
            try:
                value = json.loads(content)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"malformed JSON: {relative}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSON evidence is not an object: {relative}")
    if not REQUIRED.issubset(seen):
        raise ValueError("required proof files absent from manifest: " + ", ".join(sorted(REQUIRED - seen)))
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and path.name != MANIFEST_NAME}
    if actual != seen:
        raise ValueError("manifest does not enumerate the complete bundle")
    return {"format_version": 1, "verification_type": "runtime_proof_evidence_manifest_verification", "manifest_hash": supplied_hash, "files_verified": len(seen), "overall_verified": True}


def main() -> int:
    """Verify a bundle and emit a JSON report to standard output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        report = verify_manifest(args.bundle)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
