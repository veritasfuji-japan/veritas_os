"""Tests for the offline Trajectory-Level Admissibility Monitor helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.demo import generate_trajectory_admissibility_monitor as helper
from scripts.demo import validate_evaluation_governance_sample_bundle as validator

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/trajectory-admissibility-monitor-helper-v1"
)
RECEIPT_PATHS = [
    EXAMPLE_DIR / f"evaluation-receipt-{index}.example.json"
    for index in range(1, 4)
]
ATTRIBUTION_PATHS = [
    EXAMPLE_DIR / f"outcome-delta-attribution-{index}.example.json"
    for index in range(1, 3)
]
DRIFT_DETECTION_PATHS = [
    EXAMPLE_DIR / f"evaluation-drift-detection-{index}.example.json"
    for index in range(1, 3)
]
GENERATED_EXAMPLE_PATH = (
    EXAMPLE_DIR / "trajectory-admissibility-monitor.generated.example.json"
)
SCHEMA_PATH = Path(
    "docs/en/demo/schemas/trajectory-admissibility-monitor-v1.schema.json"
)
SCRIPT_PATH = Path(
    "scripts/demo/generate_trajectory_admissibility_monitor.py"
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_all(paths: list[Path]) -> list[dict[str, object]]:
    return [_load_json(path) for path in paths]


def _validate_generated_monitor(monitor: dict[str, object]) -> None:
    schema = _load_json(SCHEMA_PATH)
    validator._validate_payload(monitor, schema)


def _signal_types(monitor: dict[str, object]) -> set[str]:
    signals = monitor["trajectory_risk_signals"]
    assert isinstance(signals, list)
    return {signal["signal_type"] for signal in signals}


def test_generate_trajectory_monitor_from_examples() -> None:
    receipts = _load_all(RECEIPT_PATHS)
    attributions = _load_all(ATTRIBUTION_PATHS)
    drift_detections = _load_all(DRIFT_DETECTION_PATHS)

    monitor = helper.generate_trajectory_admissibility_monitor(
        receipts, attributions, drift_detections
    )

    assert monitor["schema_version"] == "trajectory-admissibility-monitor-v1"
    scope_change = monitor["admissibility_scope_change"]
    assert isinstance(scope_change, dict)
    assert scope_change["scope_expanded"] is True
    assert scope_change["expansion_type"] == "delegated_authority_expansion"
    signal_types = _signal_types(monitor)
    assert "admissibility_envelope_expansion" in signal_types
    assert "delegated_scope_widening" in signal_types
    assert "continuity_as_authorization_risk" in signal_types
    assert "strategic_admissibility_drift" in signal_types
    assert monitor["trajectory_status"] in {
        "suspicious",
        "strategically_shaped",
        "drift_detected",
        "non_deterministically_governed",
    }
    _validate_generated_monitor(monitor)


def test_generated_example_monitor_validates() -> None:
    monitor = _load_json(GENERATED_EXAMPLE_PATH)

    assert monitor["schema_version"] == "trajectory-admissibility-monitor-v1"
    _validate_generated_monitor(monitor)


def test_helper_cli_writes_schema_shaped_output(tmp_path: Path) -> None:
    output_path = tmp_path / "trajectory-admissibility-monitor.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--evaluation-receipts",
            *(str(path) for path in RECEIPT_PATHS),
            "--attributions",
            *(str(path) for path in ATTRIBUTION_PATHS),
            "--drift-detections",
            *(str(path) for path in DRIFT_DETECTION_PATHS),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Generated Trajectory-Level Admissibility Monitor v1" in completed.stdout
    monitor = _load_json(output_path)
    assert monitor["schema_version"] == "trajectory-admissibility-monitor-v1"
    _validate_generated_monitor(monitor)


def test_helper_cli_prints_json_to_stdout_when_output_omitted() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--evaluation-receipts",
            *(str(path) for path in RECEIPT_PATHS),
            "--attributions",
            *(str(path) for path in ATTRIBUTION_PATHS),
            "--drift-detections",
            *(str(path) for path in DRIFT_DETECTION_PATHS),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    monitor = json.loads(completed.stdout)
    assert monitor["schema_version"] == "trajectory-admissibility-monitor-v1"
    _validate_generated_monitor(monitor)
