"""Drift detection tests for governance observation sample fixtures.

These tests ensure the frontend-local dev fixture copy remains semantically
aligned with the root fixture used by CLI validation workflows.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT_FIXTURE_PATH = Path("fixtures/governance_observation_live_snapshot.json")
FRONTEND_FIXTURE_PATH = Path("frontend/fixtures/governance_observation_live_snapshot.json")

ARTIFACT_ID_FIELDS = (
    "decision_id",
    "bind_receipt_id",
    "execution_intent_id",
)

ROUTING_CONTEXT_FIELDS = (
    "participation_state",
    "pre_bind_source",
    "bind_reason_code",
    "bind_failure_reason",
    "failure_category",
    "target_path",
    "target_type",
    "target_label",
    "operator_surface",
    "relevant_ui_href",
)


def _load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["governance_layer_snapshot"]


def test_governance_observation_matches_between_root_and_frontend_fixture_copy() -> None:
    root_snapshot = _load_snapshot(ROOT_FIXTURE_PATH)
    frontend_snapshot = _load_snapshot(FRONTEND_FIXTURE_PATH)

    assert (
        root_snapshot["governance_observation"]
        == frontend_snapshot["governance_observation"]
    )


def test_artifact_ids_match_between_root_and_frontend_fixture_copy() -> None:
    root_snapshot = _load_snapshot(ROOT_FIXTURE_PATH)
    frontend_snapshot = _load_snapshot(FRONTEND_FIXTURE_PATH)

    for field in ARTIFACT_ID_FIELDS:
        assert root_snapshot[field] == frontend_snapshot[field]


def test_routing_context_fields_match_between_root_and_frontend_fixture_copy() -> None:
    root_snapshot = _load_snapshot(ROOT_FIXTURE_PATH)
    frontend_snapshot = _load_snapshot(FRONTEND_FIXTURE_PATH)

    for field in ROUTING_CONTEXT_FIELDS:
        assert root_snapshot[field] == frontend_snapshot[field]


def test_frontend_fixture_passes_cli_governance_observation_checker() -> None:
    result = subprocess.run(
        [
            "python",
            "scripts/check_governance_observation.py",
            str(FRONTEND_FIXTURE_PATH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "governance_observation dry-run check: valid" in result.stdout
    assert "issues: 0" in result.stdout
