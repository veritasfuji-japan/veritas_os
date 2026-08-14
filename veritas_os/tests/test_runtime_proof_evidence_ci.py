"""Focused tests for independent Runtime Proof Evidence CI tooling."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.demo.build_runtime_proof_evidence_manifest import (
    MANIFEST_NAME,
    build_manifest,
    canonical_bytes,
)
from scripts.demo.verify_runtime_proof_evidence import (
    DECISION_COMPONENTS,
    build_report,
    verify_bind_directory,
    verify_decision_report,
    verify_secret_hygiene,
)
from scripts.demo.verify_runtime_proof_evidence_manifest import verify_manifest

REPO_ROOT = Path.cwd()


def test_workflow_installs_declared_signing_extra() -> None:
    """Guard the signing dependency needed by the real Decision PoC imports."""
    workflow = (
        REPO_ROOT / ".github/workflows/runtime-proof-evidence.yml"
    ).read_text(encoding="utf-8")
    assert 'python -m pip install ".[signing]"' in workflow


def decision() -> dict[str, object]:
    """Return a minimal valid synthetic Decision Pipeline report fixture."""
    return {
        "proof_scope": "real VERITAS decision/governance runtime with controlled model output",
        "provider_mode": "controlled_provider_fixture",
        "authenticated_http_route_exercised": True,
        "route": "POST /v1/decide",
        "permission_decide_exercised": True,
        "request_validation_exercised": True,
        "controlled_provider_calls": 1,
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
        "real_runtime_components": sorted(DECISION_COMPONENTS),
    }


def write_bind(root: Path) -> None:
    """Write valid synthetic fixtures matching the existing bind contract."""
    root.mkdir()
    outcomes = {
        "committed": ("COMMITTED", 1, 0, True, False),
        "blocked": ("BLOCKED", 0, 0, False, False),
        "rolled-back": ("ROLLED_BACK", 1, 1, False, True),
    }
    for name, (outcome, actions, compensation, postcondition, compensated) in outcomes.items():
        value = {
            "scenario": name,
            "decision_stage": "synthetic_fixture",
            "real_veritas_runtime": ["execute_bind_adjudication", "WebhookBindAdapter"],
            "path": ["synthetic Decision Candidate", "Bind Boundary adjudication"],
            "final_outcome": outcome,
            "action_post_count": actions,
            "compensation_post_count": compensation,
            "external_post_occurred": actions > 0,
            "receipt_hash": "a" * 64,
            "idempotency_status": "first_execution",
            "verification_result": {"postcondition_satisfied": postcondition, "compensation_verified": compensated},
        }
        (root / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({"synthetic_data_only": True}), encoding="utf-8")


def test_valid_decision_report_passes() -> None:
    verify_decision_report(decision())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bind_invoked", True),
        ("execution_intent_created", True),
        ("outbound_provider_network_calls", 1),
        ("trustlog_append_verified", False),
        ("trustlog_chain_verified", False),
        ("replay_artifact_verified", False),
    ],
)
def test_invalid_decision_invariants_fail(field: str, value: object) -> None:
    report = decision()
    report[field] = value
    with pytest.raises(ValueError, match="invalid decision evidence"):
        verify_decision_report(report)


def test_valid_bind_scenarios_pass(tmp_path: Path) -> None:
    write_bind(tmp_path / "bind")
    verify_bind_directory(tmp_path / "bind")


@pytest.mark.parametrize(
    ("scenario", "mutation"),
    [
        ("committed", {"action_post_count": 0}),
        ("blocked", {"action_post_count": 1}),
        ("rolled-back", {"verification_result": {"postcondition_satisfied": False, "compensation_verified": False}}),
        ("committed", {"decision_stage": "real_pipeline"}),
        ("committed", {"path": ["POST /v1/decide"]}),
    ],
)
def test_invalid_bind_invariants_fail(tmp_path: Path, scenario: str, mutation: dict[str, object]) -> None:
    root = tmp_path / "bind"
    write_bind(root)
    path = root / f"{scenario}.json"
    value = json.loads(path.read_text())
    value.update(mutation)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="invalid bind evidence"):
        verify_bind_directory(root)


def make_bundle(tmp_path: Path) -> Path:
    """Create the complete minimal bundle expected by the manifest verifier."""
    root = tmp_path / "bundle"
    (root / "decision-pipeline").mkdir(parents=True)
    (root / "external-bind").mkdir()
    (root / "decision-pipeline/report.json").write_text(json.dumps(decision()))
    write_bind_contents = tmp_path / "source-bind"
    write_bind(write_bind_contents)
    for path in write_bind_contents.iterdir():
        (root / "external-bind" / path.name).write_bytes(path.read_bytes())
    verification = {"overall_verified": True, "proofs_independent": True, "decision_to_bind_connection_claimed": False}
    (root / "verification-report.json").write_text(json.dumps(verification))
    (root / "ci-context.json").write_text(json.dumps({"metadata_type": "ci_provenance_only", "generated_by": "github_actions", "commit_sha": "abc123"}))
    (root / "reviewer-summary.md").write_text("independent proofs")
    manifest = build_manifest(root, "abc123")
    (root / MANIFEST_NAME).write_text(json.dumps(manifest))
    return root


def rewrite_manifest_hash(root: Path, manifest: dict[str, object]) -> None:
    """Recalculate the aggregate hash after a deliberate structural mutation."""
    unhashed = copy.deepcopy(manifest)
    unhashed.pop("manifest_hash", None)
    manifest["manifest_hash"] = hashlib.sha256(canonical_bytes(unhashed)).hexdigest()
    (root / MANIFEST_NAME).write_text(json.dumps(manifest))


def test_valid_manifest_and_ci_provenance_pass(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    assert verify_manifest(root)["overall_verified"]
    context = json.loads((root / "ci-context.json").read_text())
    assert context["commit_sha"] == "abc123"
    assert "secret" not in json.dumps(context).lower()


def test_altered_file_fails_manifest_verification(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    (root / "reviewer-summary.md").write_text("altered")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_manifest(root)


def test_incorrect_sha_fails_manifest_verification(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    manifest = json.loads((root / MANIFEST_NAME).read_text())
    manifest["files"][0]["sha256"] = "0" * 64
    rewrite_manifest_hash(root, manifest)
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_manifest(root)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json"])
def test_path_traversal_fails(tmp_path: Path, unsafe: str) -> None:
    root = make_bundle(tmp_path)
    manifest = json.loads((root / MANIFEST_NAME).read_text())
    manifest["files"][0]["path"] = unsafe
    rewrite_manifest_hash(root, manifest)
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_manifest(root)


def test_duplicate_manifest_entry_fails(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    manifest = json.loads((root / MANIFEST_NAME).read_text())
    manifest["files"].append(copy.deepcopy(manifest["files"][0]))
    rewrite_manifest_hash(root, manifest)
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_manifest(root)


def test_missing_required_file_fails(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    (root / "external-bind/blocked.json").unlink()
    with pytest.raises(ValueError, match="missing bundled file"):
        verify_manifest(root)


def test_malformed_json_fails(tmp_path: Path) -> None:
    root = make_bundle(tmp_path)
    path = root / "ci-context.json"
    path.write_text("{")
    manifest = build_manifest(root, "abc123")
    (root / MANIFEST_NAME).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="malformed JSON"):
        verify_manifest(root)


def test_combined_report_explicitly_preserves_independence(tmp_path: Path) -> None:
    decision_path = tmp_path / "decision.json"
    decision_path.write_text(json.dumps(decision()))
    bind_dir = tmp_path / "bind"
    write_bind(bind_dir)
    report = build_report(decision_path, bind_dir)
    assert report["proofs_independent"] is True
    assert report["decision_to_bind_connection_claimed"] is False
    assert report["decision_proof"]["connected_to_bind_proof"] is False


def test_secret_hygiene_rejects_secret_fields(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text('{"api_key": "not-allowed"}')
    with pytest.raises(ValueError, match="secret hygiene"):
        verify_secret_hygiene(tmp_path)
