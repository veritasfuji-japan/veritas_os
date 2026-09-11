#!/usr/bin/env python3
"""Run the NeoMundi RGC v0.2 real-observation VERITAS PoC verifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from veritas_os.governance.neomundi_real_observation_poc import (
    NeoMundiRealObservationPocError,
    run_neomundi_real_observation_poc,
)


def _strict_json_object(raw: bytes, *, source: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key in {source}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in {source}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"top-level JSON object required in {source}")
    return value


def _load_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return _strict_json_object(raw, source=str(path)), hashlib.sha256(raw).hexdigest()


def _parse_now(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--now must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("--now must include a timezone")
    return parsed


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="RGC v0.2 JSON")
    parser.add_argument("--jwks", type=Path, required=True, help="Trusted public JWKS JSON")
    parser.add_argument(
        "--replay-state-dir",
        type=Path,
        required=True,
        help="Durable local directory used for single-use replay markers",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for verification report, sealed evidence, and manifest",
    )
    parser.add_argument(
        "--verifier-policy-id",
        default="neomundi-rgc-v02-real-observation-poc",
    )
    parser.add_argument(
        "--verifier-trust-level",
        default="external-poc",
    )
    parser.add_argument(
        "--trust-policy-id",
        default="neomundi-rgc-v02-external-poc",
    )
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        required=True,
        help="Maximum accepted age for observed_at",
    )
    parser.add_argument(
        "--max-future-skew-seconds",
        type=int,
        default=60,
    )
    parser.add_argument(
        "--allow-no-expiry",
        action="store_true",
        help=(
            "Explicitly allow RGC v0.2 evidence without expires_at for this PoC. "
            "Without this flag, the generic boundary requires expiry."
        ),
    )
    parser.add_argument(
        "--now",
        type=_parse_now,
        default=None,
        help="Optional timezone-aware ISO-8601 validation time for reproducible runs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        artifact, artifact_file_sha256 = _load_json(args.artifact)
        trusted_jwks, jwks_file_sha256 = _load_json(args.jwks)
        outputs = run_neomundi_real_observation_poc(
            artifact,
            trusted_jwks=trusted_jwks,
            replay_state_dir=args.replay_state_dir,
            verifier_policy_id=args.verifier_policy_id,
            verifier_trust_level=args.verifier_trust_level,
            trust_policy_id=args.trust_policy_id,
            max_age_seconds=args.max_age_seconds,
            max_future_skew_seconds=args.max_future_skew_seconds,
            allow_no_expiry=args.allow_no_expiry,
            now=args.now,
            source_artifact_file_sha256=artifact_file_sha256,
            trusted_jwks_file_sha256=jwks_file_sha256,
        )
    except NeoMundiRealObservationPocError as exc:
        _write_json_atomic(args.output_dir / "verification_report.json", exc.report)
        print(f"VERITAS NeoMundi PoC verification failed: {exc.reason}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        report = {
            "status": "failed",
            "stage": "input",
            "reason": str(exc),
            "claim_boundary": {
                "measurement_only": True,
                "authority_created": False,
                "human_approval_created": False,
                "bind_authorization_created": False,
                "governance_decision_created": False,
                "external_effect_performed": False,
            },
        }
        _write_json_atomic(args.output_dir / "verification_report.json", report)
        print(f"VERITAS NeoMundi PoC input failure: {exc}", file=sys.stderr)
        return 2

    _write_json_atomic(
        args.output_dir / "verification_report.json",
        outputs["verification_report"],
    )
    _write_json_atomic(
        args.output_dir / "verified_external_measurement_evidence.json",
        outputs["verified_external_measurement_evidence"],
    )
    _write_json_atomic(
        args.output_dir / "evidence_manifest.json",
        outputs["evidence_manifest"],
    )
    print(
        "VERITAS NeoMundi PoC verification succeeded: "
        f"{outputs['verified_external_measurement_evidence']['evidence']['artifact_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
