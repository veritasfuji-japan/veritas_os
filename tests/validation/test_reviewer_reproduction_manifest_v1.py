"""Offline reviewer bundle regressions; no Docker, network or provider calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess

import pytest

from scripts.validation.reviewer_reproduction_manifest_v1 import (
    BundleError,
    canonical_bytes,
    make_manifest,
    read_json,
    sha256,
    verify_bundle,
)

SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bundle(tmp_path):
    identity = {"tested_sha": SHA, "source_sha": SHA, "base_sha": SHA}
    payloads = {
        "report.json": {
            **identity,
            "result": "PASS",
            "proof": "CONTROLLED_CURRENT_HEAD_DECISION_TO_EFFECT_E2E",
            "production_claim": False,
            "production_decision_to_effect_e2e_proven": False,
            "production_validation_proven": False,
            "trustlog_exactly_once_proven": False,
        },
        "evidence.json": {**identity, "format_version": "controlled-decision-to-effect-evidence/v1"},
        "reviewer-proof-validation.json": {
            **identity, "result": "PASS_BOUNDED_CONSISTENCY_ONLY",
            "production_proven": False,
            "third_party_certified": False,
            "independent_effect_observed": False,
            "independent_custody_proven": False,
            "all_producer_predicates_independently_recomputed": False,
        },
    }
    for name, data in payloads.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    manifest = make_manifest(
        tmp_path, SHA, postgres_version="16", python_version="3.12",
    )
    (tmp_path / "reproduction-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    return tmp_path


def _replace_manifest(root, manifest):
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = sha256(canonical_bytes(manifest))
    (root / "reproduction-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_clean_bundle_is_consistent_without_claiming_independent_custody(bundle):
    result = verify_bundle(bundle, SHA)
    assert result["result"] == "PASS_BUNDLE_CONSISTENCY_ONLY"
    assert result["origin_authenticity_proven"] is False
    assert result["administrative_independence_proven"] is False
    assert result["verified_file_count"] == 3


def test_expected_sha_is_mandatory_and_out_of_band(bundle):
    with pytest.raises(BundleError, match="MANIFEST_CHECKOUT_MISMATCH"):
        verify_bundle(bundle, "b" * 40)
    with pytest.raises(BundleError, match="BAD_CHECKOUT_SHA"):
        verify_bundle(bundle, "a" * 7)


def test_separately_pinned_manifest_detects_replacement(bundle):
    digest = read_json(bundle / "reproduction-manifest.json")["manifest_sha256"]
    verify_bundle(bundle, SHA, expected_manifest_sha256=digest)
    with pytest.raises(BundleError, match="EXTERNAL_MANIFEST_PIN_MISMATCH"):
        verify_bundle(bundle, SHA, expected_manifest_sha256="b" * 64)


@pytest.mark.parametrize("filename", [
    "report.json", "evidence.json", "reviewer-proof-validation.json",
])
def test_modified_file_fails_even_if_json_remains_valid(bundle, filename):
    path = bundle / filename
    body = read_json(path)
    body["extra"] = "tampered"
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(BundleError, match="FILE_SIZE_MISMATCH|FILE_HASH_MISMATCH"):
        verify_bundle(bundle, SHA)


@pytest.mark.parametrize("field", [
    "third_party_certified", "production_proven",
    "independent_administrative_custody_proven",
])
def test_manifest_cannot_overclaim_even_with_new_self_hash(bundle, field):
    manifest = read_json(bundle / "reproduction-manifest.json")
    manifest[field] = True
    _replace_manifest(bundle, manifest)
    with pytest.raises(BundleError, match="UNSUPPORTED_MANIFEST_CLAIM"):
        verify_bundle(bundle, SHA)


def test_changed_manifest_self_hash_rejected(bundle):
    manifest = read_json(bundle / "reproduction-manifest.json")
    manifest["python_version"] = "0.0"
    (bundle / "reproduction-manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(BundleError, match="MANIFEST_HASH_MISMATCH"):
        verify_bundle(bundle, SHA)


def test_duplicate_file_entry_rejected_even_with_rehashed_manifest(bundle):
    manifest = read_json(bundle / "reproduction-manifest.json")
    manifest["files"][1] = copy.deepcopy(manifest["files"][0])
    _replace_manifest(bundle, manifest)
    with pytest.raises(BundleError, match="DUPLICATE_OR_UNEXPECTED_FILE"):
        verify_bundle(bundle, SHA)


def test_path_traversal_entry_rejected(bundle):
    manifest = read_json(bundle / "reproduction-manifest.json")
    manifest["files"][0]["path"] = "../secret.json"
    _replace_manifest(bundle, manifest)
    with pytest.raises(BundleError, match="DUPLICATE_OR_UNEXPECTED_FILE"):
        verify_bundle(bundle, SHA)


def test_missing_file_fails(bundle):
    (bundle / "evidence.json").unlink()
    with pytest.raises(BundleError, match="MISSING_OR_SYMLINKED_FILE"):
        verify_bundle(bundle, SHA)


def test_symlinked_evidence_rejected(bundle):
    path = bundle / "evidence.json"
    contents = bundle / "replacement.json"
    path.rename(contents)
    path.symlink_to(contents)
    with pytest.raises(BundleError, match="MISSING_OR_SYMLINKED_FILE"):
        verify_bundle(bundle, SHA)


def test_duplicate_json_keys_rejected(bundle):
    (bundle / "evidence.json").write_text('{"tested_sha":"a","tested_sha":"b"}')
    with pytest.raises(BundleError, match="DUPLICATE_JSON_KEY"):
        read_json(bundle / "evidence.json")


def test_false_production_claim_rejected_before_manifest_creation(bundle):
    report = bundle / "report.json"
    data = read_json(report)
    data["production_validation_proven"] = True
    report.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(BundleError, match="UNSUPPORTED_PRODUCTION_CLAIM"):
        make_manifest(bundle, SHA, postgres_version="16", python_version="3.12")


def test_runner_compose_has_no_public_ports_or_docker_socket():
    import yaml

    path = ROOT / "docker/reviewer-proof-v1/compose.yml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert config["networks"]["proof_net"]["internal"] is True
    proof = config["services"]["proof"]
    db = config["services"]["db"]
    assert proof["read_only"] is True
    assert set(proof["cap_add"]) == {"NET_BIND_SERVICE"}
    assert "ALL" in proof["cap_drop"]
    assert proof["depends_on"]["db"]["condition"] == "service_healthy"
    assert "ports" not in db and "ports" not in proof
    assert all("docker.sock" not in str(mount) for mount in proof["volumes"])
    assert any(
        mount["target"] == "/workspace" and mount["read_only"] is True
        for mount in proof["volumes"]
    )


def test_host_entrypoint_shell_syntax_is_valid():
    path = ROOT / "scripts/validation/run_reviewer_reproduction_v1.sh"
    completed = subprocess.run(
        ["bash", "-n", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
