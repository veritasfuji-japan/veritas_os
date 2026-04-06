from __future__ import annotations

import json
from pathlib import Path

import pytest

from veritas_os.policy.compiler import compile_policy_to_bundle
from veritas_os.policy.explain import build_explanation_metadata
from veritas_os.policy.models import PolicyCompilationError, PolicyValidationError
from veritas_os.policy.runtime_adapter import load_runtime_bundle

EXAMPLES_DIR = Path("policies/examples")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_compile_policy_success_generates_artifacts(tmp_path: Path) -> None:
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "high_risk_route_requires_human_review.yaml",
        tmp_path,
        compiled_at="2026-03-28T00:00:00Z",
    )

    assert result.bundle_dir.exists()
    assert result.manifest_path.exists()
    assert (result.bundle_dir / "compiled" / "canonical_ir.json").exists()
    assert (result.bundle_dir / "compiled" / "explain.json").exists()
    assert (result.bundle_dir / "signatures" / "UNSIGNED").exists()
    assert (result.bundle_dir / "manifest.sig").exists()
    assert result.archive_path.exists()


def test_compile_policy_failure_for_invalid_source(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text(
        """
        schema_version: "1.0"
        policy_id: "policy.invalid"
        version: "1"
        title: "broken"
        description: "missing scope and invalid outcome"
        outcome:
          decision: "block_all"
          reason: "invalid"
        """,
        encoding="utf-8",
    )

    with pytest.raises(PolicyValidationError):
        compile_policy_to_bundle(invalid_file, tmp_path)


def test_manifest_contents_and_explanation_metadata(tmp_path: Path) -> None:
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-03-28T01:02:03Z",
    )

    manifest = _load_json(result.manifest_path)
    explain = _load_json(result.bundle_dir / "compiled" / "explain.json")

    assert manifest["policy_id"] == "policy.external_tool_usage.denied"
    assert manifest["compiled_at"] == "2026-03-28T01:02:03Z"
    assert manifest["schema_version"] == "0.1"
    assert manifest["semantic_hash"] == result.semantic_hash
    assert manifest["outcome_summary"]["decision"] == "deny"
    assert manifest["bundle_contents"]
    assert manifest["signing"]["status"] == "signed-local"

    assert explain["purpose"]
    assert explain["application"]["human_summary"]
    assert explain["outcome"]["human_summary"]


def test_semantic_hash_stability_and_deterministic_outputs(tmp_path: Path) -> None:
    fixed_compiled_at = "2026-03-28T04:00:00Z"
    left = compile_policy_to_bundle(
        EXAMPLES_DIR / "missing_mandatory_evidence_halt.yaml",
        tmp_path / "left",
        compiled_at=fixed_compiled_at,
    )
    right = compile_policy_to_bundle(
        EXAMPLES_DIR / "missing_mandatory_evidence_halt.yaml",
        tmp_path / "right",
        compiled_at=fixed_compiled_at,
    )

    assert left.semantic_hash == right.semantic_hash

    left_manifest = _load_json(left.manifest_path)
    right_manifest = _load_json(right.manifest_path)
    left_canonical = _load_json(left.bundle_dir / "compiled" / "canonical_ir.json")
    right_canonical = _load_json(right.bundle_dir / "compiled" / "canonical_ir.json")

    # output-root path only is non-deterministic because each test run directory differs
    left_manifest["source_files"] = ["<redacted-source>"]
    right_manifest["source_files"] = ["<redacted-source>"]

    assert left_manifest == right_manifest
    assert left_canonical == right_canonical


def test_bundle_archive_is_deterministic(tmp_path: Path) -> None:
    """Tar archive must produce identical bytes across builds (normalized metadata)."""
    import hashlib

    fixed_at = "2026-03-28T04:00:00Z"
    r1 = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path / "a",
        compiled_at=fixed_at,
    )
    r2 = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path / "b",
        compiled_at=fixed_at,
    )
    h1 = hashlib.sha256(r1.archive_path.read_bytes()).hexdigest()
    h2 = hashlib.sha256(r2.archive_path.read_bytes()).hexdigest()
    assert h1 == h2, "archive should be byte-identical for same input"


def test_bundle_archive_excludes_symlinks(tmp_path: Path) -> None:
    """Symlinks in the bundle directory must not be included in the archive."""
    import tarfile

    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "low_risk_route_allow.yaml",
        tmp_path,
        compiled_at="2026-04-04T00:00:00Z",
    )
    # Inject a symlink into the bundle directory
    link = result.bundle_dir / "malicious_link"
    link.symlink_to("/etc/passwd")

    from veritas_os.policy.bundle import create_bundle_archive

    archive_path = create_bundle_archive(result.bundle_dir)
    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
    assert not any("malicious_link" in n for n in names)


def test_bundle_structure_paths_are_valid(tmp_path: Path) -> None:
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-03-28T08:00:00Z",
    )
    manifest = _load_json(result.manifest_path)

    paths = [entry["path"] for entry in manifest["bundle_contents"]]

    assert "compiled/canonical_ir.json" in paths
    assert "compiled/explain.json" in paths
    assert "signatures/UNSIGNED" in paths


def test_runtime_adapter_verifies_manifest_signature(tmp_path: Path) -> None:
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-03-28T09:00:00Z",
    )
    bundle = load_runtime_bundle(result.bundle_dir)
    assert bundle.semantic_hash == result.semantic_hash


def test_runtime_adapter_rejects_tampered_manifest_signature(tmp_path: Path) -> None:
    result = compile_policy_to_bundle(
        EXAMPLES_DIR / "external_tool_usage_denied.yaml",
        tmp_path,
        compiled_at="2026-03-28T09:10:00Z",
    )
    manifest = _load_json(result.manifest_path)
    manifest["compiler_version"] = "tampered"
    result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="signature verification failed"):
        load_runtime_bundle(result.bundle_dir)


def test_compile_wraps_io_error_as_policy_compilation_error(tmp_path: Path) -> None:
    """OSError during bundle writing surfaces as PolicyCompilationError."""
    read_only_dir = tmp_path / "readonly"
    read_only_dir.mkdir()
    read_only_dir.chmod(0o444)

    with pytest.raises(PolicyCompilationError, match="failed to write bundle artifacts"):
        compile_policy_to_bundle(
            EXAMPLES_DIR / "low_risk_route_allow.yaml",
            read_only_dir,
            compiled_at="2026-04-02T00:00:00Z",
        )


def test_compile_logs_start_and_success(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Compiler emits INFO logs at start and on success."""
    import logging

    with caplog.at_level(logging.INFO, logger="veritas_os.policy.compiler"):
        compile_policy_to_bundle(
            EXAMPLES_DIR / "low_risk_route_allow.yaml",
            tmp_path,
            compiled_at="2026-04-02T00:00:00Z",
        )

    assert "compiling policy" in caplog.text
    assert "compilation succeeded" in caplog.text
    assert "policy.low_risk_route.allow" in caplog.text


def test_compile_wraps_signing_error_as_policy_compilation_error(
    tmp_path: Path,
) -> None:
    """Invalid signing key surfaces as PolicyCompilationError."""
    with pytest.raises(PolicyCompilationError, match="Ed25519 signing failed"):
        compile_policy_to_bundle(
            EXAMPLES_DIR / "low_risk_route_allow.yaml",
            tmp_path,
            compiled_at="2026-04-02T00:00:00Z",
            signing_key=b"not-a-valid-pem-key",
        )


def test_build_explanation_metadata_handles_incomplete_ir() -> None:
    """build_explanation_metadata does not raise KeyError on incomplete IR."""
    incomplete_ir = {"policy_id": "test.incomplete"}
    result = build_explanation_metadata(incomplete_ir)
    assert result["policy_id"] == "test.incomplete"
    assert result["outcome"]["decision"] == "unknown"
    assert result["outcome"]["reason"] == ""
    assert result["requirements"]["minimum_approval_count"] == 0
    assert result["application"]["condition_count"] == 0
    assert result["application"]["constraint_count"] == 0


def test_collect_bundle_files_excludes_symlinks(tmp_path: Path) -> None:
    """collect_bundle_files must not include symlinks, consistent with create_bundle_archive."""
    from veritas_os.policy.bundle import collect_bundle_files

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    real_file = bundle_dir / "real.json"
    real_file.write_text("{}", encoding="utf-8")
    link = bundle_dir / "link.json"
    link.symlink_to(real_file)

    files = collect_bundle_files(bundle_dir)
    paths = [f["path"] for f in files]
    assert "real.json" in paths
    assert "link.json" not in paths
