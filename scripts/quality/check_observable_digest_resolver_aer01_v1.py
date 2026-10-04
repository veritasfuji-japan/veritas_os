#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / "artifacts" / "observable-digest-resolver-aer01-v1"
REPORT_PATH = ARTIFACT_ROOT / "proof-report.json"
PYTEST_LOG = ARTIFACT_ROOT / "focused-pytest.txt"

RESOLVER_PATH = "veritas_os/audit/observable_digest_resolver.py"
BEHAVIOR_TEST_PATH = "veritas_os/tests/test_observable_digest_resolver_behavior.py"
IMPLEMENTATION_MANIFEST_PATH = "security/observable_digest_resolver_minimal_behavior_implementation_v1.json"
ACTIVATION_GATE_PATH = "security/observable_digest_resolver_activation_evidence_review_v1.json"

EXPECTED = {
    RESOLVER_PATH: "64431fecf69579d8554cbc590a67ce8ca9d4a612",
    BEHAVIOR_TEST_PATH: "a247bf768ca7a0ac6f65ac13fbb2e07664336b30",
    IMPLEMENTATION_MANIFEST_PATH: "5174dab99f9284498966a4bd8968db5ec910b052",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def blob(path: str) -> str:
    return git("hash-object", path)


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

    tested_sha = git("rev-parse", "HEAD")
    observed = {path: blob(path) for path in EXPECTED}
    identity_matches = {path: observed[path] == EXPECTED[path] for path in EXPECTED}

    implementation_manifest = json.loads(
        (ROOT / IMPLEMENTATION_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    activation_gate = json.loads(
        (ROOT / ACTIVATION_GATE_PATH).read_text(encoding="utf-8")
    )
    aer01 = next(item for item in activation_gate["gates"] if item["id"] == "AER-01")

    tests = [
        BEHAVIOR_TEST_PATH,
        "veritas_os/tests/test_observable_digest_resolver_activation_evidence_review.py",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    PYTEST_LOG.write_text(proc.stdout, encoding="utf-8")

    closure = aer01.get("closure_record")
    closure_state_valid = aer01["status"] == "PROOF_PENDING_EXACT_MAIN"
    if aer01["status"] == "CLOSED_PASS":
        closure_state_valid = (
            isinstance(closure, dict)
            and closure.get("determination") == "CLOSED_PASS"
            and closure.get("exact_merged_main_sha") == "94faafa1a42fde18a3cf03c41e54e731266e82fb"
            and closure.get("workflow_run_id") == 37208356216
            and closure.get("job_id") == 111454223084
            and closure.get("artifact_id") == 11305563535
            and closure.get("artifact_sha256") == "8103465d432ef2470a887dacca70c5a76d88561ba18c5c9b090735c89ed8f989"
            and closure.get("activation_authorized") is False
            and closure.get("activation_approved") is False
            and closure.get("activation_performed") is False
            and closure.get("effect_path_connection_authorized") is False
        )

    invariants = {
        "behavior_implemented": implementation_manifest["behavior_implemented"] is True,
        "behavior_authorized_false": implementation_manifest["behavior_authorized"] is False,
        "behavior_activated_false": implementation_manifest["behavior_activated"] is False,
        "activation_gate_blocked": implementation_manifest["activation_gate"] == "BLOCKED",
        "review_activation_authorized_false": activation_gate["activation_authorized"] is False,
        "review_activation_approved_false": activation_gate["activation_approved"] is False,
        "review_activation_performed_false": activation_gate["activation_performed"] is False,
        "effect_path_connection_authorized_false": activation_gate["effect_path_connection_authorized"] is False,
        "aer01_state_is_proof_pending_or_validly_closed": closure_state_valid,
    }

    passed = all(identity_matches.values()) and all(invariants.values()) and proc.returncode == 0

    report = {
        "proof_scope": "OBSERVABLE_DIGEST_RESOLVER_AER01_EXACT_IMPLEMENTATION_IDENTITY_V1",
        "tested_sha": tested_sha,
        "github_sha_env": os.environ.get("GITHUB_SHA"),
        "result": "PASS" if passed else "FAIL",
        "proof_status": "CLOSED_PASS" if aer01["status"] == "CLOSED_PASS" else "PENDING_INDEPENDENT_CLOSURE",
        "expected_git_blob_identities": EXPECTED,
        "observed_git_blob_identities": observed,
        "identity_matches": identity_matches,
        "invariants": invariants,
        "focused_tests": tests,
        "focused_tests_passed": proc.returncode == 0,
        "python_version": sys.version,
        "platform": platform.platform(),
        "non_claims": [
            "This report does not authorize activation.",
            "This report does not approve activation.",
            "This report does not authorize effect-path connection.",
            "AER-01 may be CLOSED only when the pinned exact-main run, job, artifact and digest match the frozen independent closure record.",
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not passed:
        print(json.dumps(report, indent=2, sort_keys=True))
        print(proc.stdout)
        return 1

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
