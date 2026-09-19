from __future__ import annotations

import json
from pathlib import Path

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "cage"
    / "phase5e-review-manifest.json"
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_phase5e_manifest_binds_all_runtime_phases() -> None:
    data = _manifest()
    assert data["format_version"] == "veritas-cage-phase5e-review-packet/v1"
    assert data["status"] == "REVIEW_CANDIDATE"
    assert list(data["phases"]) == ["5A", "5B", "5C", "5D"]

    for phase, record in data["phases"].items():
        assert record["pr"] > 0, phase
        assert len(record["pr_head_sha"]) == 40, phase
        assert len(record["merge_sha"]) == 40, phase
        assert len(record["cage_sha"]) == 40, phase
        assert record["workflow_run_id"] > 0, phase
        assert record["artifact_id"] > 0, phase
        assert record["artifact_name"].startswith(f"veritas-cage-phase{phase.lower()}-")
        assert record["artifact_digest"].startswith("sha256:")
        assert len(record["artifact_digest"]) == len("sha256:") + 64


def test_phase5e_manifest_preserves_non_amplification_invariants() -> None:
    invariants = _manifest()["invariants"]
    assert invariants
    assert all(value is True for value in invariants.values())


def test_phase5e_manifest_contains_no_production_or_endorsement_claim() -> None:
    nonclaims = _manifest()["nonclaims"]
    assert nonclaims
    assert all(value is False for value in nonclaims.values())


def test_phase5e_phase5d_is_bound_to_current_merged_baseline() -> None:
    data = _manifest()
    assert (
        data["veritas_phase5e_baseline"]
        == data["phases"]["5D"]["merge_sha"]
        == "4822a5b8bfcd59af7f76e9d33da4fa8e8e74d29b"
    )
    assert (
        data["cage_latest_reviewed_main"]
        == data["phases"]["5D"]["cage_sha"]
        == "50b12e7d983db0e3d7faf206ac6aa600294f33ac"
    )
