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
        "status=0",
        "pytest -q veritas_os/tests -m slow --durations=20 --tb=short || status=$?",
        'if [ "$status" -eq 5 ]; then',
        '  echo "No slow tests were selected."',
        "  exit 0",
        "fi",
        'exit "$status"',
    ])
