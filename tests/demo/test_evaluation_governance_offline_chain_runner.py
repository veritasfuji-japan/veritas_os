"""Tests for the Evaluation Governance offline chain runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.demo import run_evaluation_governance_offline_chain as runner
from scripts.demo import validate_evaluation_governance_sample_bundle as validator

EXAMPLE_DIR = Path(
    "docs/en/demo/examples/evaluation-governance-offline-chain-v1"
)
SCRIPT_PATH = Path("scripts/demo/run_evaluation_governance_offline_chain.py")
SCHEMA_PATHS_BY_VERSION = {
    "outcome-delta-attribution-v1": Path(
        "docs/en/demo/schemas/outcome-delta-attribution-v1.schema.json"
    ),
    "evaluation-drift-detection-v1": Path(
        "docs/en/demo/schemas/evaluation-drift-detection-v1.schema.json"
    ),
    "trajectory-admissibility-monitor-v1": Path(
        "docs/en/demo/schemas/trajectory-admissibility-monitor-v1.schema.json"
    ),
    "legitimacy-impact-review-v1": Path(
        "docs/en/demo/schemas/legitimacy-impact-review-v1.schema.json"
    ),
}
GENERATED_FILE_NAMES = [
    "outcome-delta-attribution-1.generated.example.json",
    "outcome-delta-attribution-2.generated.example.json",
    "evaluation-drift-detection-1.generated.example.json",
    "evaluation-drift-detection-2.generated.example.json",
    "trajectory-admissibility-monitor.generated.example.json",
    "legitimacy-impact-review.generated.example.json",
    "chain-manifest.generated.example.json",
]


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_schema_shape(payload: dict[str, object]) -> None:
    schema_version = payload["schema_version"]
    assert isinstance(schema_version, str)
    schema_path = SCHEMA_PATHS_BY_VERSION.get(schema_version)
    if schema_path is None:
        return
    schema = _load_json(schema_path)
    validator._validate_payload(payload, schema)


def _signal_types(monitor: dict[str, object]) -> set[str]:
    signals = monitor["trajectory_risk_signals"]
    assert isinstance(signals, list)
    return {signal["signal_type"] for signal in signals}


def test_runner_imports_cleanly() -> None:
    assert callable(runner.run_offline_chain)
    assert callable(runner.load_json)
    assert callable(runner.write_json)
    assert callable(runner.canonical_json_hash)
    assert callable(runner.validate_generated_artifact)
    assert callable(runner.build_chain_manifest)


def test_run_offline_chain_generates_expected_artifacts(tmp_path: Path) -> None:
    result = runner.run_offline_chain(EXAMPLE_DIR, tmp_path)

    for file_name in GENERATED_FILE_NAMES:
        assert (tmp_path / file_name).is_file()

    attribution_1 = _load_json(
        tmp_path / "outcome-delta-attribution-1.generated.example.json"
    )
    attribution_2 = _load_json(
        tmp_path / "outcome-delta-attribution-2.generated.example.json"
    )
    drift_1 = _load_json(
        tmp_path / "evaluation-drift-detection-1.generated.example.json"
    )
    drift_2 = _load_json(
        tmp_path / "evaluation-drift-detection-2.generated.example.json"
    )
    monitor = _load_json(
        tmp_path / "trajectory-admissibility-monitor.generated.example.json"
    )
    review = _load_json(
        tmp_path / "legitimacy-impact-review.generated.example.json"
    )
    manifest = _load_json(tmp_path / "chain-manifest.generated.example.json")

    assert attribution_1["schema_version"] == "outcome-delta-attribution-v1"
    assert attribution_2["schema_version"] == "outcome-delta-attribution-v1"
    assert drift_1["schema_version"] == "evaluation-drift-detection-v1"
    assert drift_2["schema_version"] == "evaluation-drift-detection-v1"
    assert monitor["schema_version"] == "trajectory-admissibility-monitor-v1"
    assert review["schema_version"] == "legitimacy-impact-review-v1"
    assert (
        manifest["schema_version"]
        == "evaluation-governance-offline-chain-manifest-v1"
    )

    for payload in [
        attribution_1,
        attribution_2,
        drift_1,
        drift_2,
        monitor,
        review,
    ]:
        _validate_schema_shape(payload)

    assert "strategic_admissibility_drift" in _signal_types(monitor)
    assert monitor["trajectory_status"] in {
        "suspicious",
        "strategically_shaped",
        "drift_detected",
        "non_deterministically_governed",
    }
    assert review["legitimacy_impact_detected"] is True
    assert manifest["non_runtime"] is True
    assert manifest["non_enforcing"] is True
    assert result.manifest == manifest


def test_runner_cli_writes_to_output_dir(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_DIR),
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Generated Evaluation Governance offline chain v1" in completed.stdout
    assert "trajectory_status=" in completed.stdout
    assert "legitimacy_impact_detected=True" in completed.stdout
    for file_name in GENERATED_FILE_NAMES:
        assert (tmp_path / file_name).is_file()


def test_runner_cli_refuses_implicit_example_mutation() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--input-dir",
            str(EXAMPLE_DIR),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "refusing to write checked-in generated examples" in completed.stderr
