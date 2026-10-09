"""Guard the slow-suite time budget without weakening test coverage or failures."""

from pathlib import Path

import yaml


def _slow_job() -> dict:
    """Read the authoritative GitHub Actions slow-test job."""
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/main.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["test-slow"]


def test_slow_suite_has_bounded_completion_budget() -> None:
    """Installation plus the expanded suite must have a bounded one-hour budget."""
    assert _slow_job()["timeout-minutes"] == 60


def test_slow_suite_preserves_selection_and_failure_propagation() -> None:
    """The timeout fix must not skip tests or tolerate failing pytest results."""
    job = _slow_job()
    assert not job.get("continue-on-error", False)
    step = next(s for s in job["steps"] if s["name"] == "Run slow tests (if any)")
    assert not step.get("continue-on-error", False)
    assert step["run"].strip() == '\n'.join([
        "set -euxo pipefail",
        "mkdir -p test-reports",
        "status=0",
        "pytest -q veritas_os/tests -m slow --durations=20 --tb=short "
        "--junitxml=test-reports/pytest-slow.xml || status=$?",
        'if [ "$status" -eq 5 ]; then',
        '  echo "No slow tests were selected."',
        "  exit 0",
        "fi",
        'exit "$status"',
    ])


def test_slow_suite_publishes_validated_junit_without_masking_failures() -> None:
    """The complete slow suite must leave a nonempty, durable JUnit artifact."""
    steps = _slow_job()["steps"]
    run = next(s for s in steps if s["name"] == "Run slow tests (if any)")
    validate = next(s for s in steps if s["name"] == "Validate slow JUnit evidence")
    upload = next(s for s in steps if s["name"] == "Upload slow JUnit evidence")

    assert "--junitxml=test-reports/pytest-slow.xml" in run["run"]
    assert validate["run"] == (
        "python scripts/ci/validate_pytest_slow_junit.py "
        "test-reports/pytest-slow.xml"
    )
    assert not validate.get("continue-on-error", False)
    assert not upload.get("continue-on-error", False)
    assert upload["if"] == "always()"
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"]["name"] == "pytest-slow-py312"
    assert upload["with"]["path"] == "test-reports/pytest-slow.xml"
    assert upload["with"]["if-no-files-found"] == "error"
    assert steps.index(run) < steps.index(validate) < steps.index(upload)
