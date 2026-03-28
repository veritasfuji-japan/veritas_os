"""Tests for runtime data hygiene and fresh-clone behavior."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from veritas_os.core import world


def test_world_default_path_uses_runtime_namespace(monkeypatch):
    """Default world path should resolve under runtime/dev/state."""
    for key in (
        "VERITAS_WORLD_PATH",
        "VERITAS_WORLD_STATE_PATH",
        "WORLD_STATE_PATH",
        "VERITAS_DATA_DIR",
        "VERITAS_PATH",
        "VERITAS_HOME",
        "VERITAS_DIR",
        "VERITAS_RUNTIME_ENV",
    ):
        monkeypatch.delenv(key, raising=False)

    path = world._resolve_world_path()

    assert "runtime/dev/state/world_state.json" in str(path)


def test_reset_repo_runtime_dry_run_reports_candidates(tmp_path):
    """Cleanup script should list generated artifacts in dry-run mode."""
    repo_root = Path(__file__).resolve().parents[2]
    target_dir = repo_root / "runtime" / "dev" / "logs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "temp.log"
    target_file.write_text("runtime artifact", encoding="utf-8")

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "reset_repo_runtime.py"),
        "--dry-run",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    assert "runtime/dev/logs/temp.log" in result.stdout


def test_reset_repo_runtime_apply_removes_world_state_payload():
    """Apply mode should remove persisted world state artifacts."""
    repo_root = Path(__file__).resolve().parents[2]
    state_dir = repo_root / "runtime" / "dev" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    world_state = state_dir / "world_state.json"
    world_state.write_text(
        '{"projects":[{"last":{"chosen_title":"sample_title_for_cleanup"}}]}',
        encoding="utf-8",
    )

    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "reset_repo_runtime.py"),
        "--apply",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    assert not world_state.exists()
    assert (state_dir / ".gitkeep").exists()
