"""Guard slow-suite CI sharding and independent failure propagation."""

from pathlib import Path

import yaml


def _jobs() -> dict:
    root = Path(__file__).resolve().parents[2]
    return yaml.safe_load(
        (root / ".github/workflows/main.yml").read_text(encoding="utf-8")
    )["jobs"]


def test_slow_suite_preserves_bounded_full_dependency_environment() -> None:
    job = _jobs()["test-slow"]
    assert job["timeout-minutes"] == 60
    assert job["runs-on"] == "ubuntu-latest"
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["max-parallel"] == 4
    assert job["strategy"]["matrix"]["shard"] == [1, 2, 3, 4]
    assert not job.get("continue-on-error", False)
    install = next(step for step in job["steps"] if step["name"] == "Install dependencies")
    assert "-r veritas_os/requirements.txt" in install["run"]
    assert "requirements-ci.txt" not in install["run"]


def test_slow_suite_preserves_marked_collection_and_failure_propagation() -> None:
    job = _jobs()["test-slow"]
    run = next(step for step in job["steps"] if step["name"] == "Run slow tests (if any)")
    assert not run.get("continue-on-error", False)
    cmd = run["run"]
    assert "set -euxo pipefail" in cmd
    assert "python -m pytest -q veritas_os/tests -m slow" in cmd
    assert "-p scripts.ci.slow_pytest_shard" in cmd
    assert "--slow-shard-index=\"${{ matrix.shard }}\"" in cmd
    assert "--slow-shard-count=4" in cmd
    assert "--junitxml=test-reports/pytest-slow.xml" in cmd
    assert "|| true" not in cmd and "exit 0" not in cmd
    assert "|| status=" not in cmd


def test_slow_suite_uploads_both_required_artifacts_even_on_failure() -> None:
    job = _jobs()["test-slow"]
    steps = job["steps"]
    run = next(step for step in steps if step["name"] == "Run slow tests (if any)")
    validate = next(step for step in steps if step["name"] == "Validate slow JUnit evidence")
    upload = next(step for step in steps if step["name"] == "Upload slow JUnit evidence")
    assert validate["run"] == (
        "python scripts/ci/validate_pytest_slow_junit.py test-reports/pytest-slow.xml"
    )
    assert not validate.get("continue-on-error", False)
    assert upload["if"] == "always()"
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"]["name"] == "pytest-slow-py312-shard-${{ matrix.shard }}"
    assert "test-reports/pytest-slow.xml" in upload["with"]["path"]
    assert "test-reports/slow-shard-manifest.json" in upload["with"]["path"]
    assert upload["with"]["if-no-files-found"] == "error"
    assert steps.index(run) < steps.index(validate) < steps.index(upload)


def test_existing_slow_required_check_name_is_kept_at_aggregate_gate() -> None:
    job = _jobs()["test-slow-verify"]
    assert job["name"] == "test-slow (py3.12)"
    assert job["needs"] == ["test-slow"]
    assert job["if"] == "always()"
    assert not job.get("continue-on-error", False)
    steps = job["steps"]
    download = next(step for step in steps if step["name"] == "Download all slow shard evidence")
    assert download["uses"] == "actions/download-artifact@v4"
    assert download["with"]["pattern"] == "pytest-slow-py312-shard-*"
    verify = next(step for step in steps if step["name"] == "Verify complete, disjoint slow suite")
    assert verify["env"]["SHARD_RESULT"] == "${{ needs.test-slow.result }}"
    assert 'test "$SHARD_RESULT" = "success"' in verify["run"]
    assert "--shard-count 4 --min-cases 948" in verify["run"]
