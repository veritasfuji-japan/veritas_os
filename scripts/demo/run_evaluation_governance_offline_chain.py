#!/usr/bin/env python3
"""Run the synthetic Evaluation Governance offline helper chain.

This reviewer-facing demo runner composes existing offline helper functions over
local example JSON files. It is intentionally non-runtime and non-enforcing: it
never calls ``/v1/decide``, never dereferences artifact references, never uses
network access, and never imports runtime admissibility logic.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.demo.generate_evaluation_drift_detection import (
    EVALUATION_DRIFT_DETECTION_SCHEMA_PATH,
    generate_evaluation_drift_detection,
)
from scripts.demo.generate_legitimacy_impact_review import (
    LEGITIMACY_IMPACT_REVIEW_SCHEMA_PATH,
    MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH,
    generate_legitimacy_impact_review,
)
from scripts.demo.generate_outcome_delta_attribution import (
    OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH,
    generate_outcome_delta_attribution,
)
from scripts.demo.generate_trajectory_admissibility_monitor import (
    EVALUATION_RECEIPT_SCHEMA_PATH,
    TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH,
    generate_trajectory_admissibility_monitor,
)

ISSUED_AT = "2026-01-01T00:00:00Z"
CHAIN_ID = "evaluation-governance-offline-chain-example-001"
CHAIN_SCHEMA_VERSION = "evaluation-governance-offline-chain-manifest-v1"
DEFAULT_GENERATED_DIR_NAME = "generated"

INPUT_FILE_NAMES = {
    "receipt_1": "evaluation-receipt-1.example.json",
    "receipt_2": "evaluation-receipt-2.example.json",
    "receipt_3": "evaluation-receipt-3.example.json",
    "manifest_change": "manifest-change-receipt.example.json",
}
GENERATED_FILE_NAMES = {
    "attribution_1": "outcome-delta-attribution-1.generated.example.json",
    "attribution_2": "outcome-delta-attribution-2.generated.example.json",
    "drift_1": "evaluation-drift-detection-1.generated.example.json",
    "drift_2": "evaluation-drift-detection-2.generated.example.json",
    "monitor": "trajectory-admissibility-monitor.generated.example.json",
    "review": "legitimacy-impact-review.generated.example.json",
    "manifest": "chain-manifest.generated.example.json",
}
SCHEMA_PATHS_BY_VERSION = {
    "evaluation-receipt-v1": EVALUATION_RECEIPT_SCHEMA_PATH,
    "manifest-change-receipt-v1": MANIFEST_CHANGE_RECEIPT_SCHEMA_PATH,
    "outcome-delta-attribution-v1": OUTCOME_DELTA_ATTRIBUTION_SCHEMA_PATH,
    "evaluation-drift-detection-v1": EVALUATION_DRIFT_DETECTION_SCHEMA_PATH,
    "trajectory-admissibility-monitor-v1": (
        TRAJECTORY_ADMISSIBILITY_MONITOR_SCHEMA_PATH
    ),
    "legitimacy-impact-review-v1": LEGITIMACY_IMPACT_REVIEW_SCHEMA_PATH,
}


@dataclass(frozen=True)
class ChainRunResult:
    """Result metadata returned by ``run_offline_chain`` for tests and CLIs."""

    output_dir: Path
    artifacts: dict[str, dict[str, Any]]
    artifact_paths: dict[str, Path]
    manifest: dict[str, Any]


def _jsonschema_module() -> Any | None:
    """Return the optional jsonschema module when it is installed locally."""
    if importlib.util.find_spec("jsonschema") is None:
        return None

    import jsonschema

    return jsonschema


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from ``path`` with clear offline-runner errors."""
    if not path.is_file():
        raise FileNotFoundError(f"missing input file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise TypeError(f"expected JSON object in {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as stable, reviewer-readable JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)}\n",
        encoding="utf-8",
    )


def canonical_json_hash(payload: Any) -> str:
    """Return the SHA-256 digest of canonical JSON for local artifacts."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_generated_artifact(payload: dict[str, Any]) -> None:
    """Validate an artifact against its schema when jsonschema is available."""
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str):
        raise ValueError("generated artifact is missing string schema_version")

    schema_path = SCHEMA_PATHS_BY_VERSION.get(schema_version)
    if schema_path is None:
        return

    jsonschema = _jsonschema_module()
    if jsonschema is None:
        return

    schema = load_json(schema_path)
    jsonschema.Draft202012Validator(schema).validate(payload)


def _set_hashed_identifier(
    artifact: dict[str, Any],
    identifier_field: str,
    identifier: str,
    hash_field: str,
) -> dict[str, Any]:
    """Return ``artifact`` with a runner-specific identifier and hash."""
    updated = dict(artifact)
    updated[identifier_field] = identifier
    updated[hash_field] = "0" * 64
    without_hash = dict(updated)
    without_hash.pop(hash_field)
    updated[hash_field] = canonical_json_hash(without_hash)
    validate_generated_artifact(updated)
    return updated


def _artifact_ref(path: Path, output_dir: Path, input_dir: Path) -> str:
    """Build a documentation-friendly local artifact reference."""
    try:
        return path.relative_to(input_dir).as_posix()
    except ValueError:
        return path.relative_to(output_dir).as_posix()


def build_chain_manifest(
    input_dir: Path,
    output_dir: Path,
    artifact_paths: dict[str, Path],
    artifacts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the simple v1 manifest for the generated offline chain."""
    artifact_order = [
        ("receipt_1", "evaluation_receipt"),
        ("receipt_2", "evaluation_receipt"),
        ("receipt_3", "evaluation_receipt"),
        ("manifest_change", "manifest_change_receipt"),
        ("attribution_1", "outcome_delta_attribution"),
        ("attribution_2", "outcome_delta_attribution"),
        ("drift_1", "evaluation_drift_detection"),
        ("drift_2", "evaluation_drift_detection"),
        ("monitor", "trajectory_admissibility_monitor"),
        ("review", "legitimacy_impact_review"),
    ]
    manifest_artifacts = []
    for key, artifact_type in artifact_order:
        manifest_artifacts.append(
            {
                "artifact_type": artifact_type,
                "artifact_ref": _artifact_ref(
                    artifact_paths[key],
                    output_dir,
                    input_dir,
                ),
                "artifact_hash": canonical_json_hash(artifacts[key]),
            }
        )

    return {
        "schema_version": CHAIN_SCHEMA_VERSION,
        "chain_id": CHAIN_ID,
        "issued_at": ISSUED_AT,
        "non_runtime": True,
        "non_enforcing": True,
        "artifacts": manifest_artifacts,
        "chain_summary": (
            "Synthetic offline Evaluation Governance chain generated for "
            "reviewer-facing architecture review."
        ),
        "non_goals": [
            "does_not_change_runtime_behavior",
            "does_not_establish_legitimacy",
            "does_not_certify_compliance",
            "does_not_call_v1_decide",
            "does_not_dereference_artifact_refs",
        ],
    }


def run_offline_chain(input_dir: Path, output_dir: Path) -> ChainRunResult:
    """Generate the complete synthetic offline governance chain.

    Args:
        input_dir: Directory containing the local example input artifacts.
        output_dir: Directory where generated artifacts should be written.

    Returns:
        Metadata for generated artifacts and the chain manifest.

    Raises:
        FileNotFoundError: If required local input files are missing.
        ValueError: If JSON is invalid or optional schema validation fails.
        jsonschema.ValidationError: If jsonschema is installed and schema
            validation fails for an input or generated artifact.
    """
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()

    input_paths = {
        key: input_dir / file_name
        for key, file_name in INPUT_FILE_NAMES.items()
    }
    generated_paths = {
        key: output_dir / file_name
        for key, file_name in GENERATED_FILE_NAMES.items()
    }

    receipts = [
        load_json(input_paths["receipt_1"]),
        load_json(input_paths["receipt_2"]),
        load_json(input_paths["receipt_3"]),
    ]
    manifest_change = load_json(input_paths["manifest_change"])
    for artifact in [*receipts, manifest_change]:
        validate_generated_artifact(artifact)

    attribution_1 = generate_outcome_delta_attribution(receipts[0], receipts[1])
    attribution_1 = _set_hashed_identifier(
        attribution_1,
        "attribution_id",
        "evaluation-governance-offline-chain-attribution-001",
        "attribution_hash",
    )
    attribution_2 = generate_outcome_delta_attribution(receipts[1], receipts[2])
    attribution_2 = _set_hashed_identifier(
        attribution_2,
        "attribution_id",
        "evaluation-governance-offline-chain-attribution-002",
        "attribution_hash",
    )

    drift_1 = generate_evaluation_drift_detection(attribution_1)
    drift_1 = _set_hashed_identifier(
        drift_1,
        "detection_id",
        "evaluation-governance-offline-chain-drift-detection-001",
        "detection_hash",
    )
    drift_2 = generate_evaluation_drift_detection(attribution_2)
    drift_2 = _set_hashed_identifier(
        drift_2,
        "detection_id",
        "evaluation-governance-offline-chain-drift-detection-002",
        "detection_hash",
    )

    attributions = [attribution_1, attribution_2]
    drift_detections = [drift_1, drift_2]
    monitor = generate_trajectory_admissibility_monitor(
        receipts,
        attributions,
        drift_detections,
    )
    review = generate_legitimacy_impact_review(manifest_change, monitor)
    validate_generated_artifact(review)

    artifacts = {
        "receipt_1": receipts[0],
        "receipt_2": receipts[1],
        "receipt_3": receipts[2],
        "manifest_change": manifest_change,
        "attribution_1": attribution_1,
        "attribution_2": attribution_2,
        "drift_1": drift_1,
        "drift_2": drift_2,
        "monitor": monitor,
        "review": review,
    }
    artifact_paths = {**input_paths, **generated_paths}
    manifest = build_chain_manifest(input_dir, output_dir, artifact_paths, artifacts)
    artifacts["manifest"] = manifest

    for key in GENERATED_FILE_NAMES:
        write_json(generated_paths[key], artifacts[key])

    return ChainRunResult(
        output_dir=output_dir,
        artifacts=artifacts,
        artifact_paths=generated_paths,
        manifest=manifest,
    )


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the offline chain runner."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate the non-runtime, non-enforcing Evaluation Governance "
            "offline helper chain from local example inputs."
        )
    )
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--write-example-output",
        action="store_true",
        help=(
            "Intentionally overwrite the input example directory's generated/ "
            "artifacts. Required when --output-dir is omitted."
        ),
    )
    return parser.parse_args()


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    """Resolve the requested output directory while preventing mutations."""
    if args.output_dir is not None:
        return args.output_dir
    if args.write_example_output:
        return args.input_dir / DEFAULT_GENERATED_DIR_NAME
    raise ValueError(
        "refusing to write checked-in generated examples without "
        "--write-example-output; pass --output-dir for safe temporary output"
    )


def main() -> int:
    """Run the Evaluation Governance offline chain CLI."""
    args = _parse_args()
    try:
        output_dir = _resolve_output_dir(args)
        result = run_offline_chain(args.input_dir, output_dir)
    except Exception as exc:  # noqa: BLE001 - CLI presents concise errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1

    monitor = result.artifacts["monitor"]
    review = result.artifacts["review"]
    print(
        "Generated Evaluation Governance offline chain v1: "
        f"{result.output_dir} "
        f"(generated_artifacts={len(GENERATED_FILE_NAMES)}, "
        f"trajectory_status={monitor['trajectory_status']}, "
        f"legitimacy_impact_detected={review['legitimacy_impact_detected']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
