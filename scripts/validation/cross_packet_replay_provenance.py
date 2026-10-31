#!/usr/bin/env python3
"""Bounded, read-only, offline cross-packet replay and claimed-provenance audit.

This checks ONLY the exact set of locally supplied v0.2 profiles. It is NOT a
durable replay registry, issuer authenticity check, signed evidence validation,
runtime execution proof, or third-party audit. No network, state or writes.
"""

from __future__ import annotations

import argparse
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Sequence

from scripts.validation.validate_audit_evidence_profile import (
    V02_PROFILE_VERSION,
    verify as verify_profile,
)
from veritas_os.governance.evidence_chain_manifest import (
    EvidenceChainManifest,
    validate_evidence_chain_manifest,
)
from veritas_os.security.hash import (
    canonical_json_dumps,
    sha256_of_canonical_json,
)

REPORT_VERSION = "veritas.audit-cross-packet-replay-provenance/0.1"
MAX_PACKETS = 64
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_CASES_PER_PACKET = 512
MAX_EVIDENCE_PER_PACKET = 1024
HEX_256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT_OUTCOMES = {"commit", "committed", "commit_eligible"}
IDENTITY_FIELDS = (
    ("decision_id", "decision_id"),
    ("intent_id", "execution_intent_id"),
    ("authority_id", "authority_evidence_id"),
    ("approval_id", "human_approval_receipt_id"),
    ("bind_receipt_id", "bind_receipt_id"),
    ("effect_receipt_id", "outcome_receipt_id"),
)
NAMED_HASH_FIELDS = {
    "authority_id": "authority_evidence_hash",
    "approval_id": "human_approval_receipt_hash",
    "bind_receipt_id": "bind_receipt_hash",
    "effect_receipt_id": "outcome_receipt_hash",
}
PROVENANCE_METADATA = {
    "audit_packet_id": "packet_id",
    "source_repository": "repository",
    "source_commit": "source_commit",
}
COVERAGE_LIMITATIONS = [
    "Only explicitly supplied packet paths are checked; omitted history is invisible.",
    "Results and snapshot digests are local, self-contained integrity observations.",
    "Caller-supplied expected digests are not independent notarization or signatures.",
    "Matched manifest metadata and profile claims do not authenticate the issuer.",
    "No persistent replay prevention, atomic admission, or cross-run state is provided.",
    "No actual runtime effect, authority validity, custody or independent review is proven.",
    "Concurrent file mutation and root replacement are not an atomic snapshot.",
]


def _parts(relative: str) -> tuple[str, ...]:
    """Validate a strict POSIX relative file path (no symlinks on open)."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("unsafe relative path")
    parts = tuple(relative.split("/"))
    if any(part in ("", ".", "..") for part in parts) or relative.startswith("/"):
        raise ValueError("unsafe relative path")
    if len(parts) > 32 or len(relative) > 2048:
        raise ValueError("path exceeds bounded depth")
    return parts


def _read_under_root(root: Path, relative: str) -> bytes:
    """Read bounded regular file using directory-relative O_NOFOLLOW opens."""
    parts = _parts(relative)
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise OSError("safe descriptor-relative open is unsupported")
    dflags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fflags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    directory_fd = None
    file_fd = None
    try:
        directory_fd = os.open(root, dflags)
        for part in parts[:-1]:
            next_fd = os.open(part, dflags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(parts[-1], fflags, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise ValueError("not a bounded regular file")
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(file_fd, min(65536, MAX_FILE_BYTES + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise ValueError("file exceeds byte limit")
            chunks.append(chunk)
        after = os.fstat(file_fd)
        if (
            size != before.st_size or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            raise ValueError("file changed during read")
        return b"".join(chunks)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _finding(
    findings: list[dict[str, str]],
    *,
    kind: str,
    code: str,
    path: str,
    case_id: str = "",
) -> None:
    findings.append({"kind": kind, "code": code, "path": path, "case_id": case_id})


def _read_manifest(
    *,
    root: Path,
    profile_relative: str,
    evidence: dict[str, Any],
) -> tuple[EvidenceChainManifest | None, str]:
    """Read and check canonical local manifest bytes against profile SHA-256."""
    prefix = profile_relative.rpartition("/")[0]
    relative = "/".join(part for part in (prefix, evidence["relative_path"]) if part)
    raw = _read_under_root(root, relative)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != evidence["sha256"]:
        raise ValueError("MANIFEST_EVIDENCE_HASH_MISMATCH")
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("not a JSON object")
        if set(payload) != {field.name for field in fields(EvidenceChainManifest)}:
            raise ValueError("manifest has missing or unknown fields")
        manifest = EvidenceChainManifest(**payload)
        # Dataclasses do not enforce runtime annotation types. Refuse malformed
        # JSON values before asking canonicalization or existing validators to
        # interpret them as strings, iterables or collection metadata.
        for name in (
            "manifest_id", "decision_id", "execution_intent_id", "operation_id",
            "final_outcome", "chain_status", "action_class", "target_system",
            "target_resource", "generated_at", "manifest_hash",
        ):
            if not isinstance(getattr(manifest, name), str):
                raise ValueError("wrong manifest field type")
        if (
            not isinstance(manifest.human_approval_required, bool)
            or not isinstance(manifest.metadata, dict)
            or not isinstance(manifest.requested_scope, list)
            or not isinstance(manifest.missing_links, list)
            or not isinstance(manifest.refusal_basis, list)
            or not isinstance(manifest.observed_effects_summary, list)
        ):
            raise ValueError("wrong manifest collection type")
        if raw != canonical_json_dumps(manifest.to_dict()).encode("utf-8"):
            raise ValueError("noncanonical manifest bytes")
        validated = validate_evidence_chain_manifest(manifest)
        if not validated.is_valid:
            raise ValueError("invalid manifest structure")
        if manifest.manifest_hash != manifest.deterministic_digest():
            raise ValueError("manifest digest mismatch")
    except (TypeError, KeyError, AttributeError, ValueError, RecursionError, OverflowError) as exc:
        raise ValueError("INVALID_CANONICAL_MANIFEST") from exc
    return manifest, digest


def _analyze_case(
    *,
    root: Path,
    relative: str,
    profile: dict[str, Any],
    case: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
    findings: list[dict[str, str]],
) -> dict[str, Any] | None:
    """Bind v0.2 case to local manifest and compare declared origin metadata."""
    case_id = case["case_id"]
    operation = case["operation_id"]
    manifest_id = case["manifest_id"]
    manifest_eid = case["manifest_evidence_id"]
    if operation is None:
        _finding(findings, kind="INCOMPLETE", code="UNBOUND_CASE", path=relative, case_id=case_id)
        return None
    if (
        not operation or not manifest_id or not manifest_eid
        or manifest_eid not in evidence or manifest_eid not in case["evidence_ids"]
    ):
        _finding(findings, kind="FAIL", code="CASE_MANIFEST_BINDING_INVALID", path=relative, case_id=case_id)
        return None
    try:
        manifest, sha = _read_manifest(
            root=root, profile_relative=relative, evidence=evidence[manifest_eid]
        )
    except (OSError, ValueError, UnicodeError, RecursionError, OverflowError):
        _finding(findings, kind="FAIL", code="MANIFEST_EVIDENCE_INVALID", path=relative, case_id=case_id)
        return None
    assert manifest is not None
    if manifest.operation_id != operation or manifest.manifest_id != manifest_id:
        _finding(findings, kind="FAIL", code="OPERATION_OR_MANIFEST_MISMATCH", path=relative, case_id=case_id)
        return None
    for profile_key, manifest_key in IDENTITY_FIELDS:
        declared = case.get(profile_key)
        actual = getattr(manifest, manifest_key)
        if profile_key in ("decision_id", "intent_id") and not declared:
            _finding(findings, kind="INCOMPLETE", code="REQUIRED_DECISION_INTENT_MISSING", path=relative, case_id=case_id)
            return None
        if declared is not None and declared != actual:
            _finding(findings, kind="FAIL", code="CASE_MANIFEST_LINK_ID_MISMATCH", path=relative, case_id=case_id)
            return None
        if declared and profile_key in NAMED_HASH_FIELDS and not getattr(manifest, NAMED_HASH_FIELDS[profile_key]):
            _finding(findings, kind="INCOMPLETE", code="NAMED_LINK_HASH_MISSING", path=relative, case_id=case_id)
            return None
    if manifest.chain_status == "complete" and manifest.final_outcome.lower().strip() not in COMMIT_OUTCOMES:
        _finding(findings, kind="FAIL", code="CHAIN_OUTCOME_STATUS_CONTRADICTION", path=relative, case_id=case_id)
        return None

    scope = profile["scope"]
    claimed = {
        "packet_id": profile["packet_id"],
        "repository": scope["repository"],
        "source_commit": scope["source_commit"],
    }
    provenance_status = "CLAIMED_CONTEXT_MATCHES_LOCAL_MANIFEST"
    metadata = manifest.metadata if isinstance(manifest.metadata, dict) else {}
    for meta_key, claim_key in PROVENANCE_METADATA.items():
        metadata_value = metadata.get(meta_key)
        if not isinstance(metadata_value, str) or not metadata_value:
            _finding(findings, kind="INCOMPLETE", code="PROVENANCE_METADATA_MISSING", path=relative, case_id=case_id)
            provenance_status = "PROVENANCE_UNBOUND"
        elif metadata_value != claimed[claim_key]:
            _finding(findings, kind="FAIL", code="PROVENANCE_METADATA_MISMATCH", path=relative, case_id=case_id)
            provenance_status = "PROVENANCE_CONFLICT"
    return {
        "path": relative,
        "packet_id": claimed["packet_id"],
        "case_id": case_id,
        "repository": claimed["repository"],
        "source_commit": claimed["source_commit"],
        "operation_id": operation,
        "manifest_id": manifest_id,
        "manifest_evidence_id": manifest_eid,
        "manifest_sha256": sha,
        "local_manifest_binding": "MATCHED",
        "declared_provenance_binding": provenance_status,
        "origin_authentication": "NOT_PERFORMED",
        "independent_review": "NOT_PERFORMED",
    }


def verify_cross_packet_replay_provenance(
    *,
    packet_root: Path | str,
    profile_paths: Sequence[str],
    expected_snapshot_digest: str | None = None,
) -> dict[str, Any]:
    """Audit a complete *caller-supplied* set of local v0.2 packet paths.

    Read-only. Reuse/conflict is checked within this call's explicit paths,
    including namespace-qualified operation and manifest IDs. It cannot
    determine whether earlier, omitted or separately stored packets exist.
    """
    root = Path(packet_root)
    findings: list[dict[str, str]] = []
    packets: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    if (
        isinstance(profile_paths, (str, bytes))
        or not isinstance(profile_paths, (list, tuple))
        or not 1 <= len(profile_paths) <= MAX_PACKETS
    ):
        _finding(findings, kind="FAIL", code="INVALID_PACKET_SET", path="")
        names: list[str] = []
    else:
        names = sorted(profile_paths) if all(isinstance(x, str) for x in profile_paths) else []
        if not names:
            _finding(findings, kind="FAIL", code="INVALID_PACKET_PATHS", path="")
        elif len(names) != len(set(names)):
            _finding(findings, kind="FAIL", code="DUPLICATE_INPUT_PATH", path="")

    for relative in names:
        try:
            _parts(relative)
            raw_profile = _read_under_root(root, relative)
            profile = json.loads(raw_profile)
            if not isinstance(profile, dict) or profile.get("profile_version") != V02_PROFILE_VERSION:
                raise ValueError("v0.2 profile required")
            if (
                not isinstance(profile.get("cases"), list)
                or not isinstance(profile.get("evidence"), list)
                or len(profile["cases"]) > MAX_CASES_PER_PACKET
                or len(profile["evidence"]) > MAX_EVIDENCE_PER_PACKET
            ):
                raise ValueError("invalid or excessive case/evidence count")
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            _finding(findings, kind="FAIL", code="UNREADABLE_OR_UNSUPPORTED_PROFILE", path=relative)
            continue
        try:
            errors = verify_profile(profile, root / relative)
        except (OSError, ValueError, KeyError, TypeError, RecursionError, OverflowError):
            errors = ["validator exception"]
        if errors:
            _finding(findings, kind="FAIL", code="PROFILE_VALIDATION_FAILED", path=relative)
            continue

        packets.append({
            "path": relative,
            "packet_id": profile["packet_id"],
            "profile_sha256": hashlib.sha256(raw_profile).hexdigest(),
            "repository": profile["scope"]["repository"],
            "source_commit": profile["scope"]["source_commit"],
            "acquisition_method": profile["scope"]["acquisition_method"],
            "provenance_claim": "SELF_DECLARED_NOT_AUTHENTICATED",
        })
        inventory = {item["id"]: item for item in profile["evidence"]}
        for case in profile["cases"]:
            link = _analyze_case(
                root=root, relative=relative, profile=profile, case=case,
                evidence=inventory, findings=findings,
            )
            if link is not None:
                links.append(link)

    # Check repeats *across distinct supplied packet files*. Identical bytes
    # are not implicitly deduplicated into one admissible record.
    for key, name, namespace in (
        ("packet_id", "PACKET_ID_REUSED", False),
        ("operation_id", "OPERATION_ID_REUSED", True),
        ("manifest_id", "MANIFEST_ID_REUSED", True),
        ("manifest_sha256", "MANIFEST_BYTES_REUSED", False),
    ):
        seen: dict[tuple[str, ...], str] = {}
        rows = packets if key == "packet_id" else links
        for row in rows:
            value = row[key]
            scoped = (row["repository"], value) if namespace else (value,)
            prior = seen.get(scoped)
            if prior is not None and prior != row["path"]:
                _finding(findings, kind="REPLAY", code=name, path=row["path"], case_id=row.get("case_id", ""))
            else:
                seen[scoped] = row["path"]

    packets.sort(key=lambda item: item["path"])
    links.sort(key=lambda item: (item["path"], item["case_id"]))
    findings = sorted(
        {canonical_json_dumps(item): item for item in findings}.values(),
        key=lambda item: (item["path"], item["case_id"], item["kind"], item["code"]),
    )
    snapshot = {"requested_paths": names, "packets": packets, "links": links, "findings": findings}
    snapshot_digest = sha256_of_canonical_json(snapshot)
    digest_comparison = "NOT_REQUESTED"
    if expected_snapshot_digest is not None:
        if not isinstance(expected_snapshot_digest, str) or not HEX_256.fullmatch(expected_snapshot_digest):
            _finding(findings, kind="FAIL", code="INVALID_EXPECTED_DIGEST", path="")
            digest_comparison = "INVALID"
        elif snapshot_digest != expected_snapshot_digest:
            _finding(findings, kind="FAIL", code="SNAPSHOT_DIGEST_MISMATCH", path="")
            digest_comparison = "MISMATCH"
        else:
            digest_comparison = "MATCHED_CALLER_SUPPLIED_DIGEST"
    findings.sort(key=lambda item: (item["path"], item["case_id"], item["kind"], item["code"]))
    if not links:
        _finding(findings, kind="INCOMPLETE", code="NO_BOUND_OPERATIONS", path="")
        findings.sort(key=lambda item: (item["path"], item["case_id"], item["kind"], item["code"]))
    kinds = {item["kind"] for item in findings}
    status = (
        "FAIL" if "FAIL" in kinds else
        "REPLAY_DETECTED" if "REPLAY" in kinds else
        "INCOMPLETE" if "INCOMPLETE" in kinds else "PASS"
    )
    return {
        "report_version": REPORT_VERSION,
        "status": status,
        "coverage": "EXPLICIT_CALLER_SUPPLIED_PACKETS_ONLY",
        "input_count": len(names),
        "validated_packet_count": len(packets),
        "bound_case_count": len(links),
        "snapshot_digest": snapshot_digest,
        "expected_digest_comparison": digest_comparison,
        "packet_records": packets,
        "link_records": links,
        "findings": findings,
        "external_origin_authenticated": False,
        "external_snapshot_anchor_verified": False,
        "limitations": list(COVERAGE_LIMITATIONS),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("profile_paths", nargs="+")
    parser.add_argument("--expected-snapshot-digest")
    args = parser.parse_args(argv)
    report = verify_cross_packet_replay_provenance(
        packet_root=args.packet_root, profile_paths=args.profile_paths,
        expected_snapshot_digest=args.expected_snapshot_digest,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2 if report["status"] == "INCOMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
