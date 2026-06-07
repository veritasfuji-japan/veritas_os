#!/usr/bin/env python3
"""Generate a reviewer packet from an offline Evaluation Governance chain.

This helper is intentionally local/offline and non-enforcing. It reads a chain
manifest produced by the Evaluation Governance offline chain runner, maps the
manifest's local artifact metadata into Reviewer Evidence Packet v1 attachment
entries, and emits a synthetic reviewer-facing packet. It does not call runtime
paths, does not dereference external artifact references, and does not establish
legitimacy or certify compliance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_PACKET_SCHEMA_PATH = (
    REPO_ROOT / "docs/en/demo/schemas/reviewer-evidence-packet-v1.schema.json"
)
REVIEWER_PACKET_TEMPLATE_PATH = (
    REPO_ROOT
    / "docs/en/demo/examples"
    / "reviewer-evidence-packet-with-evaluation-governance-v1.json"
)
SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")

ARTIFACT_TYPE_MAP = {
    "evaluation_receipt": "evaluation_receipt",
    "manifest_change_receipt": "manifest_change_receipt",
    "outcome_delta_attribution": "outcome_delta_attribution",
    "evaluation_drift_detection": "evaluation_drift_detection",
    "trajectory_admissibility_monitor": "trajectory_admissibility_monitor",
    "legitimacy_impact_review": "legitimacy_impact_review",
}

SCHEMA_REFS_BY_ARTIFACT_TYPE = {
    "evaluation_receipt": "docs/en/demo/schemas/evaluation-receipt-v1.schema.json",
    "manifest_change_receipt": (
        "docs/en/demo/schemas/manifest-change-receipt-v1.schema.json"
    ),
    "outcome_delta_attribution": (
        "docs/en/demo/schemas/outcome-delta-attribution-v1.schema.json"
    ),
    "evaluation_drift_detection": (
        "docs/en/demo/schemas/evaluation-drift-detection-v1.schema.json"
    ),
    "trajectory_admissibility_monitor": (
        "docs/en/demo/schemas/trajectory-admissibility-monitor-v1.schema.json"
    ),
    "legitimacy_impact_review": (
        "docs/en/demo/schemas/legitimacy-impact-review-v1.schema.json"
    ),
}

REVIEWER_NOTES = [
    (
        "This packet is a synthetic offline reviewer evidence packet generated "
        "from an Evaluation Governance offline chain manifest."
    ),
    (
        "Evaluation Governance artifacts are attached as optional reviewer "
        "evidence and are not runtime enforcement inputs."
    ),
    (
        "This helper does not call /v1/decide, change runtime admissibility, "
        "or introduce fail-closed behavior."
    ),
    (
        "This packet does not prove legitimacy, certify compliance, or include "
        "secrets, PII, customer data, or live external service data."
    ),
]


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when available locally."""
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object from ``path`` with clear helper errors."""
    if not path.is_file():
        raise FileNotFoundError(f"missing chain manifest or JSON file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def canonical_json_hash(payload: Any) -> str:
    """Return the SHA-256 digest of canonical JSON for local artifacts."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def map_artifact_type(chain_artifact_type: str) -> str:
    """Map a chain artifact type to a Reviewer Evidence Packet artifact type."""
    mapped_type = ARTIFACT_TYPE_MAP.get(chain_artifact_type)
    if mapped_type is None:
        supported = ", ".join(sorted(ARTIFACT_TYPE_MAP))
        raise ValueError(
            "unsupported Evaluation Governance chain artifact_type "
            f"{chain_artifact_type!r}; supported types: {supported}"
        )
    return mapped_type


def schema_ref_for_artifact_type(artifact_type: str) -> str:
    """Return the Reviewer Evidence Packet schema_ref for ``artifact_type``."""
    schema_ref = SCHEMA_REFS_BY_ARTIFACT_TYPE.get(artifact_type)
    if schema_ref is None:
        raise ValueError(f"no schema_ref mapping for artifact_type {artifact_type!r}")
    return schema_ref


def _is_external_ref(artifact_ref: str) -> bool:
    parsed = urlparse(artifact_ref)
    return bool(parsed.scheme and parsed.scheme not in {"", "file"})


def _local_artifact_path(artifact_base_dir: Path, artifact_ref: str) -> Path:
    """Return a safe local path for ``artifact_ref`` below artifact_base_dir."""
    artifact_path = Path(artifact_ref)
    if artifact_path.is_absolute():
        raise ValueError(
            f"artifact_ref must be relative for local hash computation: {artifact_ref}"
        )

    base = artifact_base_dir.resolve()
    candidate = (base / artifact_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(
            f"artifact_ref escapes artifact_base_dir: {artifact_ref}"
        ) from exc
    return candidate


def _hash_local_artifact(artifact_base_dir: Path, artifact_ref: str) -> str:
    """Compute a local artifact hash without dereferencing external refs."""
    if _is_external_ref(artifact_ref):
        raise ValueError(
            "cannot compute artifact_hash for external artifact_ref without "
            f"dereferencing it: {artifact_ref}"
        )

    artifact_path = _local_artifact_path(artifact_base_dir, artifact_ref)
    if not artifact_path.is_file():
        raise FileNotFoundError(
            "missing local artifact file needed to compute artifact_hash: "
            f"{artifact_path}"
        )

    try:
        return canonical_json_hash(load_json(artifact_path))
    except (TypeError, ValueError):
        return hashlib.sha256(artifact_path.read_bytes()).hexdigest()


def _artifact_hash(
    manifest_artifact: dict[str, Any],
    artifact_base_dir: Path,
    artifact_ref: str,
) -> str:
    candidate_hash = manifest_artifact.get("artifact_hash")
    if isinstance(candidate_hash, str) and SHA256_HEX_PATTERN.fullmatch(
        candidate_hash
    ):
        return candidate_hash
    if candidate_hash is not None:
        raise ValueError(
            "artifact_hash must be a sha256 hex string when present for "
            f"artifact_ref {artifact_ref!r}"
        )
    return _hash_local_artifact(artifact_base_dir, artifact_ref)


def build_evaluation_governance_artifacts(
    chain_manifest: dict[str, Any], artifact_base_dir: Path
) -> list[dict[str, Any]]:
    """Build Reviewer Evidence Packet Evaluation Governance attachments."""
    artifacts = chain_manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("chain manifest must contain an artifacts array")

    reviewer_artifacts: list[dict[str, Any]] = []
    for index, manifest_artifact in enumerate(artifacts):
        if not isinstance(manifest_artifact, dict):
            raise TypeError(f"chain manifest artifacts[{index}] must be an object")

        chain_artifact_type = manifest_artifact.get("artifact_type")
        artifact_ref = manifest_artifact.get("artifact_ref")
        if not isinstance(chain_artifact_type, str) or not chain_artifact_type:
            raise ValueError(f"chain manifest artifacts[{index}] missing artifact_type")
        if not isinstance(artifact_ref, str) or not artifact_ref:
            raise ValueError(f"chain manifest artifacts[{index}] missing artifact_ref")

        artifact_type = map_artifact_type(chain_artifact_type)
        reviewer_artifacts.append(
            {
                "artifact_type": artifact_type,
                "artifact_ref": artifact_ref,
                "artifact_hash": _artifact_hash(
                    manifest_artifact,
                    artifact_base_dir,
                    artifact_ref,
                ),
                "schema_ref": schema_ref_for_artifact_type(artifact_type),
                "required_for_review": False,
            }
        )

    return reviewer_artifacts


def _sanitize_synthetic_template_values(payload: Any) -> Any:
    """Remove email-shaped demo strings from the reused packet template."""
    replacements = {
        "contractor:external.user@example.test": "synthetic_offline_resource",
        "human:manager.alex": "human:synthetic_reviewer",
        "engineering_manager": "synthetic_reviewer",
    }
    if isinstance(payload, dict):
        return {
            key: _sanitize_synthetic_template_values(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [_sanitize_synthetic_template_values(value) for value in payload]
    if isinstance(payload, str):
        return replacements.get(payload, payload)
    return payload


def _packet_hash(packet: dict[str, Any]) -> str:
    """Compute Reviewer Evidence Packet hash excluding packet_hash itself."""
    payload = copy.deepcopy(packet)
    payload.pop("packet_hash", None)
    return canonical_json_hash(payload)


def validate_reviewer_packet(packet: dict[str, Any]) -> None:
    """Validate generated packet against Reviewer Evidence Packet v1 if possible."""
    jsonschema = _jsonschema_module()
    if jsonschema is None:
        return

    schema = load_json(REVIEWER_PACKET_SCHEMA_PATH)
    try:
        jsonschema.Draft202012Validator(schema).validate(packet)
    except jsonschema.ValidationError as exc:
        raise ValueError(
            f"Reviewer Evidence Packet schema validation failed: {exc}"
        ) from exc


def generate_reviewer_evidence_packet_from_chain(
    chain_manifest: dict[str, Any], artifact_base_dir: Path
) -> dict[str, Any]:
    """Generate a Reviewer Evidence Packet v1 from an offline chain manifest.

    The returned packet is synthetic, local/offline-only, and non-enforcing. It
    preserves the existing Reviewer Evidence Packet v1 shape while replacing
    Evaluation Governance attachments with artifacts listed in the chain
    manifest.
    """
    reviewer_artifacts = build_evaluation_governance_artifacts(
        chain_manifest,
        artifact_base_dir,
    )
    chain_id = chain_manifest.get("chain_id", "evaluation-governance-chain")
    issued_at = chain_manifest.get("issued_at", "2026-01-01T00:00:00Z")

    packet = _sanitize_synthetic_template_values(
        load_json(REVIEWER_PACKET_TEMPLATE_PATH)
    )
    packet["demo_id"] = "evaluation_governance_offline_chain_reviewer_packet_v1"
    packet["generated_at"] = issued_at
    packet["title"] = "Evaluation Governance Offline Chain Reviewer Evidence Packet"
    packet["summary"] = (
        "Synthetic local/offline reviewer packet generated from Evaluation "
        f"Governance offline chain manifest {chain_id!r}. It attaches chain "
        "artifacts as optional reviewer evidence and does not establish "
        "legitimacy or certify compliance."
    )
    packet["boundary_note"] = (
        "local/offline synthetic reviewer evidence only; no /v1/decide call, "
        "runtime admissibility change, live service integration, legitimacy "
        "determination, or compliance certification"
    )
    packet["local_offline_only"] = True
    packet["evaluation_governance_artifacts"] = reviewer_artifacts
    packet["reviewer_notes"] = list(REVIEWER_NOTES)
    packet["packet_hash"] = _packet_hash(packet)

    validate_reviewer_packet(packet)
    return packet


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic Reviewer Evidence Packet from an offline "
            "Evaluation Governance chain manifest."
        )
    )
    parser.add_argument(
        "--chain-manifest",
        required=True,
        type=Path,
        help="Path to the Evaluation Governance offline chain manifest JSON.",
    )
    parser.add_argument(
        "--artifact-base-dir",
        required=True,
        type=Path,
        help="Base directory for resolving local chain artifact refs if needed.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path; stdout is used when omitted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the offline reviewer packet helper."""
    args = _parse_args(argv)
    try:
        chain_manifest = load_json(args.chain_manifest)
        packet = generate_reviewer_evidence_packet_from_chain(
            chain_manifest,
            args.artifact_base_dir,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must present clear errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output is None:
        print(json.dumps(packet, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _write_json(args.output, packet)
        print(
            "Generated Reviewer Evidence Packet from Evaluation Governance "
            f"offline chain: {args.output} "
            f"({len(packet['evaluation_governance_artifacts'])} artifacts)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
