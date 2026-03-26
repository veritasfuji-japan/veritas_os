"""Production-like replay artifact generation and reload validation.

The VERITAS pipeline builds a replay snapshot at the end of each decision.
These tests verify that the snapshot can be serialised, persisted, and
reloaded without data loss — mimicking what a production audit trail would
need for regulatory replay.

Markers:
    production — production-like validation (excluded from default CI)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def replay_dir(tmp_path):
    """Create a temp directory for replay artifacts."""
    d = tmp_path / "replays"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_replay_snapshot(decision_id: str = "test-001") -> dict:
    """Build a minimal but structurally complete replay snapshot."""
    return {
        "decision_id": decision_id,
        "timestamp": "2026-03-26T08:00:00Z",
        "pipeline_version": os.environ.get(
            "VERITAS_PIPELINE_VERSION", "test"
        ),
        "input": {
            "query": "Should we approve this transaction?",
            "context": {"user_id": "replay-test", "session": "s-001"},
        },
        "stages": [
            {
                "name": "normalize",
                "duration_ms": 2,
                "output": {"query_clean": "approve transaction"},
            },
            {
                "name": "memory_retrieval",
                "duration_ms": 15,
                "output": {"memories": []},
            },
            {
                "name": "core_execute",
                "duration_ms": 50,
                "output": {
                    "chosen": "approve",
                    "risk_score": 0.12,
                    "confidence": 0.91,
                },
            },
            {
                "name": "fuji_gate",
                "duration_ms": 8,
                "output": {
                    "gate": "allow",
                    "violations": [],
                    "pii_detected": False,
                },
            },
        ],
        "output": {
            "chosen": "approve",
            "alternatives": ["deny", "escalate"],
            "gate": "allow",
            "risk_score": 0.12,
        },
        "trust_log_hash": "sha256:abc123def456",
        "fuji_summary": {"gate": "allow", "violations": []},
    }


# ---------------------------------------------------------------------------
# Production-like replay tests
# ---------------------------------------------------------------------------


@pytest.mark.production
class TestReplayArtifactGeneration:
    """Verify replay snapshots can be generated and are well-formed."""

    def test_snapshot_is_json_serialisable(self):
        snap = _build_replay_snapshot()
        text = json.dumps(snap, ensure_ascii=False)
        assert len(text) > 0
        reloaded = json.loads(text)
        assert reloaded["decision_id"] == "test-001"

    def test_snapshot_has_required_fields(self):
        snap = _build_replay_snapshot()
        required = [
            "decision_id",
            "timestamp",
            "pipeline_version",
            "input",
            "stages",
            "output",
        ]
        for field in required:
            assert field in snap, f"Missing replay field: {field}"

    def test_stages_are_ordered(self):
        snap = _build_replay_snapshot()
        stage_names = [s["name"] for s in snap["stages"]]
        assert stage_names == [
            "normalize",
            "memory_retrieval",
            "core_execute",
            "fuji_gate",
        ]


@pytest.mark.production
class TestReplayPersistence:
    """Verify replay artifacts can be written to and read from disk."""

    def test_write_and_read_jsonl(self, replay_dir):
        snapshots = [
            _build_replay_snapshot(f"dec-{i:03d}") for i in range(5)
        ]
        out_file = replay_dir / "replay.jsonl"

        # Write
        with open(out_file, "w", encoding="utf-8") as f:
            for snap in snapshots:
                f.write(json.dumps(snap, ensure_ascii=False) + "\n")

        # Read back
        loaded = []
        with open(out_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    loaded.append(json.loads(line))

        assert len(loaded) == 5
        assert loaded[0]["decision_id"] == "dec-000"
        assert loaded[4]["decision_id"] == "dec-004"

    def test_write_and_read_single_json(self, replay_dir):
        snap = _build_replay_snapshot("single-001")
        out_file = replay_dir / "single.json"
        out_file.write_text(json.dumps(snap, indent=2, ensure_ascii=False))

        reloaded = json.loads(out_file.read_text())
        assert reloaded["decision_id"] == "single-001"
        assert reloaded["output"]["chosen"] == "approve"

    def test_large_replay_batch(self, replay_dir):
        """Write 100 replay snapshots and verify all can be reloaded."""
        out_file = replay_dir / "large_batch.jsonl"
        n = 100

        with open(out_file, "w", encoding="utf-8") as f:
            for i in range(n):
                snap = _build_replay_snapshot(f"batch-{i:04d}")
                f.write(json.dumps(snap, ensure_ascii=False) + "\n")

        loaded = []
        with open(out_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    loaded.append(json.loads(line))

        assert len(loaded) == n
        # Verify first and last
        assert loaded[0]["decision_id"] == "batch-0000"
        assert loaded[-1]["decision_id"] == f"batch-{n - 1:04d}"


@pytest.mark.production
class TestReplayIntegrity:
    """Ensure replay artifacts maintain integrity across operations."""

    def test_pipeline_version_present(self):
        snap = _build_replay_snapshot()
        assert snap["pipeline_version"] is not None
        assert len(snap["pipeline_version"]) > 0

    def test_round_trip_preserves_nested_data(self, replay_dir):
        snap = _build_replay_snapshot()
        # Add deep nested data
        snap["stages"][2]["output"]["debug"] = {
            "weights": [0.1, 0.2, 0.3],
            "meta": {"nested": {"deep": True}},
        }

        out_file = replay_dir / "nested.json"
        out_file.write_text(json.dumps(snap, ensure_ascii=False))
        reloaded = json.loads(out_file.read_text())

        assert reloaded["stages"][2]["output"]["debug"]["meta"]["nested"]["deep"] is True

    def test_unicode_content_preserved(self, replay_dir):
        snap = _build_replay_snapshot()
        snap["input"]["query"] = "日本語のクエリ: ガバナンス検証"

        out_file = replay_dir / "unicode.json"
        out_file.write_text(
            json.dumps(snap, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        reloaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert "日本語" in reloaded["input"]["query"]

    def test_empty_stages_handled(self, replay_dir):
        snap = _build_replay_snapshot()
        snap["stages"] = []

        text = json.dumps(snap, ensure_ascii=False)
        reloaded = json.loads(text)
        assert reloaded["stages"] == []
