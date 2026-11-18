"""Integration tests for the secure Decision-to-external-Bind proof."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.run_decision_to_external_bind_poc import (
    _DeterministicKmsClient,
    _DeterministicObjectLockClient,
)

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts/run_decision_to_external_bind_poc.py"
)


def _run(report_path: Path, *options: str) -> dict[str, object]:
    """Run one proof in an isolated interpreter and return its report."""
    subprocess.run(
        [sys.executable, str(SCRIPT), "--report", str(report_path), *options],
        cwd=SCRIPT.parents[1],
        check=True,
    )
    return json.loads(report_path.read_text(encoding="utf-8"))


def test_supported_import_orders_do_not_cycle() -> None:
    """The policy bridge must not recreate the API schema import cycle."""
    commands = (
        "import veritas_os.api.server; import veritas_os.policy.decision_candidate",
        "import veritas_os.policy.decision_candidate; import veritas_os.api.server",
    )
    for command in commands:
        subprocess.run(
            [sys.executable, "-c", command],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
        )


def test_secure_external_client_doubles_fail_closed() -> None:
    """Synthetic infrastructure rejects malformed signing and mirror calls."""
    kms = _DeterministicKmsClient("expected-key")
    with pytest.raises(ValueError, match="unexpected synthetic KMS"):
        kms.sign(
            KeyId="wrong-key",
            Message=b"payload",
            MessageType="RAW",
            SigningAlgorithm="EDDSA",
        )

    mirror = _DeterministicObjectLockClient()
    with pytest.raises(ValueError, match="retention metadata missing"):
        mirror.put_object(Bucket="bucket", Key="key", Body=b"entry")


def test_positive_decision_to_external_bind_proof(tmp_path: Path) -> None:
    """A real CDA reaches one synthetic POST and a lineage-bound receipt."""
    report_path = tmp_path / "positive.json"

    report = _run(report_path)
    assert report["runtime_posture"] == "secure"
    assert report["secure_posture_startup_passed"] is True
    assert report["posture_validation_bypassed"] is False
    assert report["external_infrastructure_mode"] == "deterministic_test_doubles"
    assert report["secure_test_infrastructure_exercised"] is True
    assert report["kms_sign_call_count"] > 0
    assert report["object_lock_put_call_count"] > 0
    assert report["canonical_decision_verified"] is True
    assert report["execution_intent_lineage_verified"] is True
    assert report["authority_evidence_verified"] is True
    assert report["runtime_authority_status"] == "pass"
    assert report["runtime_authority_recommended_outcome"] == "commit"
    assert report["bind_adjudication_invoked"] is True
    assert report["webhook_bind_adapter_invoked"] is True
    assert report["authorization_consumption_exercised"] is True
    assert report["external_post_count"] == 1
    assert report["bind_final_outcome"] == "COMMITTED"
    assert report["decision_to_bind_receipt_lineage_verified"] is True
    assert report["result"] == "pass"


def test_invalid_authority_blocks_before_bind(tmp_path: Path) -> None:
    """Strict authority failure invokes neither Bind nor the local endpoint."""
    report_path = tmp_path / "negative.json"

    report = _run(report_path, "--negative-authority")
    assert report["secure_posture_startup_passed"] is True
    assert report["secure_test_infrastructure_exercised"] is True
    assert report["canonical_decision_verified"] is True
    assert report["runtime_authority_status"] == "fail"
    assert report["runtime_authority_recommended_outcome"] == "block"
    assert report["bind_adjudication_invoked"] is False
    assert report["bind_adjudication_call_count"] == 0
    assert report["webhook_bind_adapter_invoked"] is False
    assert report["webhook_bind_adapter_call_count"] == 0
    assert report["external_post_count"] == 0
    assert report["bind_receipt_created"] is False
    assert report["result"] == "pass"


def test_live_capture_uses_writable_governance_state(tmp_path: Path) -> None:
    """A read-only source checkout must still support isolated decision capture."""
    output = tmp_path / "decision.json"
    code = """
from pathlib import Path
import errno
import sys
from unittest.mock import patch
from veritas_os.tests.helpers.live_decision_capture import capture

source_api = Path("veritas_os/api").resolve()
real_open = Path.open

def read_only_source(path, mode="r", *args, **kwargs):
    if path.parent.resolve() == source_api and any(flag in mode for flag in "wax+"):
        raise OSError(errno.EROFS, "Read-only source checkout")
    return real_open(path, mode, *args, **kwargs)

with patch.object(Path, "open", read_only_source):
    capture(Path(sys.argv[1]))
"""
    subprocess.run(
        [sys.executable, "-c", code, str(output)],
        cwd=SCRIPT.parents[1],
        check=True,
        timeout=180,
    )
    captured = json.loads(output.read_bytes())
    assert captured["pipeline_ok"] is True
    assert captured["canonical_decision_artifact"]
    assert (tmp_path / "runtime" / "governance.json.lock").exists()
    assert json.loads((tmp_path / "runtime" / "governance.json").read_bytes()) == json.loads(
        (SCRIPT.parents[1] / "veritas_os/api/governance.json").read_bytes()
    )
