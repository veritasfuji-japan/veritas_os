"""Capture a real /v1/decide response in an isolated test interpreter.

Only model output and cloud clients are controlled. Route, kernel, signed
policy verification and CDA construction execute normally. A separate synthetic
admin credential performs the strict-startup resume through the real management
Bind path. This helper issues no candidate execution authorization or human
receipt, and does not execute the selected candidate.
"""

from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import secrets
import sys
from unittest.mock import patch

from scripts import run_decision_to_external_bind_poc as poc


def capture(
    output: Path, *, required_human_approval: bool = False,
    candidate_overrides: dict | None = None,
) -> None:
    """Write only the synthetic decision and infrastructure observations."""
    runtime = output.parent / "runtime"
    runtime.mkdir()
    poc._configure_environment(
        runtime,
        "test-" + secrets.token_urlsafe(24),
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    )
    key_id = poc._configure_secure_test_infrastructure(
        runtime, "test-" + secrets.token_urlsafe(32)
    )
    bundle = poc._configure_verified_policy_bundle(runtime)
    from veritas_os.api import governance

    policy_path = runtime / "governance.json"
    policy_path.write_bytes(governance._DEFAULT_POLICY_PATH.read_bytes())
    with (
        patch.object(governance, "_DEFAULT_POLICY_PATH", policy_path),
        patch.object(governance, "_POLICY_HISTORY_PATH", runtime / "governance_history.jsonl"),
    ):
        from veritas_os.core import pipeline

        candidate = replace(
            poc._candidate(),
            evidence_refs=["synthetic:local-review-input"],
            required_human_approval=required_human_approval,
        )
        if candidate_overrides:
            candidate = replace(candidate, **candidate_overrides)
        with (
            patch.object(poc, "_candidate", return_value=candidate),
            patch.object(pipeline, "REPLAY_SOURCE_DIR", runtime / "replay-sources"),
        ):
            response, pipeline_ok, calls = poc._decide(
                aws_clients=poc._DeterministicAwsClients(
                    poc._DeterministicKmsClient(key_id),
                    poc._DeterministicObjectLockClient(),
                ),
                policy_bundle_dir=bundle,
            )
    output.write_text(
        json.dumps(
            {
                "canonical_decision_artifact": response["canonical_decision_artifact"],
                "candidate": response["chosen"],
                "observed_at": datetime.now(UTC).isoformat(),
                "pipeline_ok": pipeline_ok,
                "infrastructure_calls": calls,
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    # Isolated test interpreter: avoid inheriting the fake runtime/KMS
    # environment into other pytest cases in the parent interpreter.
    iam = "--synthetic-iam-grant" in sys.argv[2:]
    capture(
        Path(sys.argv[1]),
        required_human_approval=iam or "--human-required" in sys.argv[2:],
        candidate_overrides=(
            {
                "intended_action": "grant_admin_role",
                "target_system": "isolated-iam-target",
                "target_resource": "contractor-001",
                "required_authority": ["saas:grant_admin"],
                "required_human_approval": True,
            }
            if iam else None
        ),
    )
