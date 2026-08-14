#!/usr/bin/env python3
"""Fail-closed validation of two independent runtime proof outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DECISION_SCOPE = "real VERITAS decision/governance runtime with controlled model output"
DECISION_COMPONENTS = {
    "routes_decide.decide", "run_decide_pipeline", "kernel.decide",
    "FUJI", "ValueCore", "TrustLog",
}
BIND_COMPONENTS = {"execute_bind_adjudication", "WebhookBindAdapter"}
BIND_FILES = ("committed.json", "blocked.json", "rolled-back.json", "manifest.json")


def load_object(path: Path) -> dict[str, Any]:
    """Load a JSON object, rejecting missing, malformed, or non-object input."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def verify_decision_report(report: dict[str, Any]) -> None:
    """Validate the existing Decision Pipeline PoC report contract."""
    expected = {
        "proof_scope": DECISION_SCOPE,
        "provider_mode": "controlled_provider_fixture",
        "authenticated_http_route_exercised": True,
        "route": "POST /v1/decide",
        "permission_decide_exercised": True,
        "request_validation_exercised": True,
        "outbound_provider_network_calls": 0,
        "trustlog_append_verified": True,
        "trustlog_chain_verified": True,
        "replay_artifact_verified": True,
        "execution_authority_claimed": False,
        "execution_intent_created": False,
        "bind_invoked": False,
        "webhook_bind_adapter_invoked": False,
        "external_effect_occurred": False,
        "human_approval_fabricated": False,
        "authority_evidence_fabricated": False,
    }
    failures = [key for key, value in expected.items() if report.get(key) != value]
    calls = report.get("controlled_provider_calls")
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 1:
        failures.append("controlled_provider_calls")
    components = report.get("real_runtime_components")
    if not isinstance(components, list) or not DECISION_COMPONENTS.issubset(components):
        failures.append("real_runtime_components")
    if failures:
        raise ValueError("invalid decision evidence: " + ", ".join(sorted(set(failures))))


def verify_bind_directory(bind_dir: Path) -> dict[str, dict[str, Any]]:
    """Validate the bind PoC manifest and all three scenario artifacts."""
    for name in BIND_FILES:
        if not (bind_dir / name).is_file():
            raise ValueError(f"missing bind proof file: {name}")
    manifest = load_object(bind_dir / "manifest.json")
    if manifest.get("synthetic_data_only") is not True:
        raise ValueError("bind manifest must disclose synthetic-only data")
    scenarios = {name: load_object(bind_dir / f"{name}.json") for name in ("committed", "blocked", "rolled-back")}
    requirements = {
        "committed": ("COMMITTED", 1, 0, True),
        "blocked": ("BLOCKED", 0, 0, False),
        "rolled-back": ("ROLLED_BACK", 1, 1, False),
    }
    for name, evidence in scenarios.items():
        outcome, actions, compensations, postcondition = requirements[name]
        verification = evidence.get("verification_result")
        components = evidence.get("real_veritas_runtime")
        path = evidence.get("path")
        valid = (
            evidence.get("scenario") == name
            and evidence.get("decision_stage") == "synthetic_fixture"
            and evidence.get("final_outcome") == outcome
            and evidence.get("action_post_count") == actions
            and evidence.get("compensation_post_count") == compensations
            and evidence.get("external_post_occurred") is (actions > 0)
            and isinstance(verification, dict)
            and verification.get("postcondition_satisfied") is postcondition
            and isinstance(components, list)
            and BIND_COMPONENTS.issubset(components)
            and isinstance(path, list)
            and all("/v1/decide" not in str(item) for item in path)
            and isinstance(evidence.get("receipt_hash"), str)
            and len(evidence["receipt_hash"]) == 64
            and isinstance(evidence.get("idempotency_status"), str)
        )
        if name == "rolled-back":
            valid = valid and verification.get("compensation_verified") is True
        if not valid:
            raise ValueError(f"invalid bind evidence: {name}")
    return scenarios


def verify_secret_hygiene(root: Path) -> None:
    """Reject obvious secret-bearing fields or authorization headers in a bundle."""
    forbidden = (b"authorization: bearer", b"x-veritas-signature", b'"api_key"', b'"encryption_key"', b"test-only-external-bind-poc-secret")
    for path in root.rglob("*"):
        if path.is_file():
            lowered = path.read_bytes().lower()
            if any(token in lowered for token in forbidden):
                raise ValueError(f"proof-bundle secret hygiene failure: {path.relative_to(root)}")


def build_report(decision_path: Path, bind_dir: Path) -> dict[str, Any]:
    """Verify both inputs and return an explicit independent-proof report."""
    verify_decision_report(load_object(decision_path))
    scenarios = verify_bind_directory(bind_dir)
    verify_secret_hygiene(decision_path.parent)
    verify_secret_hygiene(bind_dir)
    return {
        "format_version": 1,
        "verification_type": "independent_runtime_proof_bundle_verification",
        "decision_proof": {"verified": True, "connected_to_bind_proof": False},
        "bind_proof": {
            "verified": True,
            "decision_stage": "synthetic_fixture",
            "scenario_outcomes": {key: value["final_outcome"] for key, value in scenarios.items()},
        },
        "proofs_independent": True,
        "cross_proof_connection_claimed": False,
        "decision_to_bind_connection_claimed": False,
        "execution_authority_claimed_from_decide": False,
        "proof_bundle_secret_hygiene_verified": True,
        "overall_verified": True,
    }


def main() -> int:
    """Validate arguments and write the machine-readable verification report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-report", required=True, type=Path)
    parser.add_argument("--bind-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.decision_report, args.bind_dir)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
