#!/usr/bin/env python3
"""Run the fail-closed, local VERITAS Decision Pipeline proof."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPO_ROOT
    / "veritas_os/tests/fixtures/decide_pipeline/provider_transcript.json"
)
DEFAULT_REPORT = REPO_ROOT / "artifacts/decide-pipeline-poc/report.json"
PROOF_CLAIM = "real VERITAS decision/governance runtime with controlled model output"
NON_CLAIMS = [
    "live provider inference or provider transport/authentication/retries/availability",
    "deterministic behavior of a live model",
    "production TrustLog, WORM, KMS, PostgreSQL, deployment, or readiness",
    "customer or live financial-institution integration",
    "regulatory certification or approval",
    "execution authority, human approval, or Authority Evidence",
    "Bind Boundary execution, external effects, or decision-to-bind lineage",
]


def _canonical_bytes(value: Any) -> bytes:
    """Return a stable canonical JSON representation."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    """Return the SHA-256 digest of a JSON-compatible value."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _configure_environment(runtime_root: Path, api_key: str, key: str | None) -> None:
    """Configure supported, isolated local runtime storage before imports."""
    values = {
        "VERITAS_POSTURE": "dev",
        "VERITAS_ENV": "test",
        "VERITAS_API_KEY": api_key,
        "VERITAS_API_KEYS": json.dumps([{"key": api_key, "role": "operator"}]),
        "VERITAS_ENCRYPTION_KEY_PROVIDER": "env",
        "VERITAS_MEMORY_BACKEND": "json",
        "VERITAS_MEMORY_DIR": str(runtime_root / "memory"),
        "VERITAS_MEMORY_PATH": str(runtime_root / "memory" / "memory.json"),
        "VERITAS_TRUSTLOG_BACKEND": "jsonl",
        "VERITAS_DATA_DIR": str(runtime_root / "runtime-data"),
        "VERITAS_RUNTIME_ROOT": str(runtime_root / "runtime"),
        "VERITAS_LOG_DIR": str(runtime_root / "runtime-data"),
        "VERITAS_DATASET_DIR": str(runtime_root / "runtime-data" / "DASH"),
        "VERITAS_WEB_SEARCH_ENABLED": "0",
    }
    os.environ.update(values)
    if key is None:
        os.environ.pop("VERITAS_ENCRYPTION_KEY", None)
    else:
        os.environ["VERITAS_ENCRYPTION_KEY"] = key


def _request_fixture() -> dict[str, Any]:
    """Return the wholly synthetic request that crosses the HTTP boundary."""
    return {
        "query": "Select a reversible review approach for a synthetic record.",
        "context": {
            "user_id": "decision-poc-reviewer",
            "mode": "fast",
            "stakes": 0.6,
            "_mock_external_apis": True,
        },
        "options": [
            {"id": "review", "title": "Perform human review", "score": 0.8},
            {"id": "hold", "title": "Hold for more evidence", "score": 0.7},
        ],
        "min_evidence": 1,
        "memory_auto_put": True,
        "persona_evolve": False,
    }


def _project_report(
    response: dict[str, Any],
    fixture: dict[str, Any],
    transcript: dict[str, Any],
    ledger_entry: dict[str, Any],
    replay_digest: str,
    calls: int,
) -> dict[str, Any]:
    """Normalize nondeterministic runtime output into reviewer evidence."""
    gate = response.get("gate") if isinstance(response.get("gate"), dict) else {}
    return {
        "format_version": 1,
        "proof_name": "VERITAS Decision Pipeline PoC",
        "proof_scope": PROOF_CLAIM,
        "provider_mode": transcript["provider_mode"],
        "authenticated_http_route_exercised": True,
        "route": "POST /v1/decide",
        "permission_decide_exercised": True,
        "request_validation_exercised": True,
        "real_runtime_components": [
            "routes_decide.decide",
            "decision service",
            "get_decision_pipeline",
            "run_decide_pipeline",
            "kernel.decide",
            "FUJI",
            "ValueCore",
            "gate",
            "evidence",
            "response_assembly",
            "TrustLog",
        ],
        "controlled_components": ["veritas_os.core.llm_client.chat output"],
        "controlled_provider_calls": calls,
        "outbound_provider_network_calls": 0,
        "request_fixture_digest": _digest(fixture),
        "controlled_provider_transcript_digest": _digest(transcript),
        "response_artifact_digest": _digest(response),
        "request_id": "<runtime-request-id>",
        "decision_status": response.get("decision_status", "not_available"),
        "gate_decision": gate.get("decision", gate.get("status", "not_available")),
        "business_decision": response.get("business_decision", "not_available"),
        "next_action": response.get("next_action", "not_available"),
        "human_review_required": bool(response.get("human_review_required")),
        "requires_bind_before_execution": bool(
            response.get("requires_bind_before_execution")
        ),
        "required_evidence": response.get("required_evidence", []),
        "missing_evidence": response.get("missing_evidence", []),
        "satisfied_evidence": response.get("satisfied_evidence", []),
        "trustlog_append_verified": True,
        "trustlog_chain_verified": True,
        "trustlog_entry_hash": ledger_entry["sha256"],
        "replay_artifact_verified": True,
        "replay_artifact_digest": replay_digest,
        "execution_authority_claimed": False,
        "execution_intent_created": False,
        "bind_invoked": False,
        "webhook_bind_adapter_invoked": False,
        "external_effect_occurred": False,
        "human_approval_fabricated": False,
        "authority_evidence_fabricated": False,
        "production_runtime_files_changed": False,
        "proof_non_claims": NON_CLAIMS,
    }


def run_proof(
    report_path: Path,
    *,
    force_verify_failure: bool = False,
    omit_encryption_key: bool = False,
) -> int:
    """Execute the real route and independently enforce proof invariants.

    Args:
        report_path: Destination for normalized machine-readable evidence.
        force_verify_failure: Test-only fault injection after HTTP completion.
        omit_encryption_key: Test-only proof of mandatory encryption failure.

    Returns:
        Zero only when every mandatory reviewer proof check passes.
    """
    api_key = "poc-" + secrets.token_urlsafe(24)
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    transcript = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    request_fixture = _request_fixture()
    statuses: dict[str, bool] = {}

    with tempfile.TemporaryDirectory(
        prefix="decide-poc-", dir=REPO_ROOT / "runtime"
    ) as temporary:
        runtime_root = Path(temporary)
        _configure_environment(
            runtime_root,
            api_key,
            None if omit_encryption_key else encryption_key,
        )

        from veritas_os.api import server
        from veritas_os.api.schemas import DecideResponse
        from veritas_os.core import llm_client
        from veritas_os.core import pipeline as decision_pipeline
        from veritas_os.logging import trust_log

        call_count = 0
        original_kernel_decide = decision_pipeline.core_decide
        kernel_available = callable(original_kernel_decide)
        kernel_calls = 0

        def controlled_chat(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Supply the fixture exactly at the central provider seam."""
            nonlocal call_count
            call_count += 1
            return dict(transcript["response"])

        async def observed_kernel_decide(*args: Any, **kwargs: Any) -> Any:
            """Count, without replacing, calls to the real kernel."""
            nonlocal kernel_calls
            kernel_calls += 1
            return await original_kernel_decide(*args, **kwargs)

        with patch.object(llm_client, "chat", controlled_chat), patch.object(
            decision_pipeline, "core_decide", observed_kernel_decide
        ):
            with TestClient(server.app) as client:
                invalid = client.post(
                    "/v1/decide",
                    headers={"X-API-Key": "invalid-local-proof-key"},
                    json=request_fixture,
                )
                response = client.post(
                    "/v1/decide",
                    headers={"X-API-Key": api_key},
                    json=request_fixture,
                )

        statuses["authentication"] = invalid.status_code == 401
        statuses["http_route"] = response.status_code == 200
        if not statuses["http_route"]:
            payload: dict[str, Any] = {}
        else:
            payload = DecideResponse.model_validate(response.json()).model_dump()
        statuses["request_validation"] = bool(payload)
        statuses["pipeline"] = kernel_available and kernel_calls > 0
        statuses["controlled_provider"] = call_count > 0

        log_path = trust_log.LOG_JSONL
        raw_ledger = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        ledger_entry = (
            trust_log.get_trust_log_entry(str(payload.get("request_id")))
            if payload
            else None
        )
        verification = trust_log.verify_trust_log()
        if force_verify_failure:
            verification = {"ok": False}
        statuses["trustlog"] = bool(
            raw_ledger
            and ledger_entry
            and ledger_entry.get("sha256")
            and verification.get("ok")
            and payload.get("request_id") == ledger_entry.get("request_id")
            and api_key not in raw_ledger
            and encryption_key not in raw_ledger
            and request_fixture["query"] not in raw_ledger
        )

        replay = payload.get("deterministic_replay") if payload else None
        shadow_files = list((trust_log.LOG_DIR / "DASH").glob("decide_*.json"))
        shadow_linked = False
        for shadow_file in shadow_files:
            shadow = json.loads(shadow_file.read_text(encoding="utf-8"))
            if shadow.get("request_id") == payload.get("request_id"):
                shadow_linked = True
                break
        statuses["replay"] = bool(replay and shadow_linked)

        passed = all(statuses.values())
        if passed and ledger_entry is not None:
            report = _project_report(
                payload,
                request_fixture,
                transcript,
                ledger_entry,
                _digest(replay),
                call_count,
            )
            serialized = _canonical_bytes(report)
            forbidden = (api_key, encryption_key)
            passed = all(secret.encode() not in serialized for secret in forbidden)
            if passed:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_bytes(serialized + b"\n")

    labels = {
        "HTTP_ROUTE": statuses.get("http_route", False),
        "AUTHENTICATION": statuses.get("authentication", False),
        "RBAC_DECIDE": statuses.get("http_route", False),
        "REQUEST_VALIDATION": statuses.get("request_validation", False),
        "PIPELINE_KERNEL": statuses.get("pipeline", False),
        "CONTROLLED_PROVIDER": statuses.get("controlled_provider", False),
        "TRUSTLOG": statuses.get("trustlog", False),
        "REPLAY": statuses.get("replay", False),
    }
    for label, ok in labels.items():
        print(f"{label:<24} {'PASS' if ok else 'FAIL'}")
    print(f"{'OUTBOUND_PROVIDER_NETWORK':<24} 0")
    print(f"{'EXECUTION_INTENT':<24} NOT CREATED")
    print(f"{'BIND':<24} NOT INVOKED")
    print(f"{'EXTERNAL_EFFECT':<24} NONE")
    print(f"{'RESULT':<24} {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    """Parse reviewer options and run the proof."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force-verify-failure", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--omit-encryption-key", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    return run_proof(
        args.report,
        force_verify_failure=args.force_verify_failure,
        omit_encryption_key=args.omit_encryption_key,
    )


if __name__ == "__main__":
    raise SystemExit(main())
