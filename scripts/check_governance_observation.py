#!/usr/bin/env python3
"""CLI dry-run checker for governance_observation fixture JSON.

This script validates schema and semantic consistency for
``governance_layer_snapshot.governance_observation`` payloads without
changing runtime governance behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from veritas_os.api.schemas import GovernanceObservation
from veritas_os.governance.observation_evaluator import evaluate_governance_observation


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run validate governance_observation semantics from a JSON file."
        )
    )
    parser.add_argument("json_file", type=Path, help="Path to fixture/payload JSON file")
    return parser


def _load_observation_payload(json_file: Path) -> dict:
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"file not found: {json_file}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from None

    snapshot = data.get("governance_layer_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("governance_layer_snapshot not found or is not an object")

    observation = snapshot.get("governance_observation")
    if not isinstance(observation, dict):
        raise ValueError("governance_observation not found at governance_layer_snapshot")

    return observation


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        observation_payload = _load_observation_payload(args.json_file)
        observation = GovernanceObservation(**observation_payload)
    except ValidationError as exc:
        print("governance_observation dry-run check: invalid", file=sys.stderr)
        print(f"file: {args.json_file}", file=sys.stderr)
        print("ERROR SCHEMA_VALIDATION_FAILED:", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1
    except ValueError as exc:
        print("governance_observation dry-run check: invalid", file=sys.stderr)
        print(f"file: {args.json_file}", file=sys.stderr)
        print(f"ERROR INPUT: {exc}", file=sys.stderr)
        return 1

    result = evaluate_governance_observation(observation)
    has_errors = any(issue.severity == "error" for issue in result.issues)

    status = "invalid" if has_errors else "valid"
    stream = sys.stderr if has_errors else sys.stdout
    print(f"governance_observation dry-run check: {status}", file=stream)
    print(f"file: {args.json_file}", file=stream)
    print(f"issues: {len(result.issues)}", file=stream)

    for issue in result.issues:
        print(f"{issue.severity.upper()} {issue.code}: {issue.message}", file=stream)

    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
