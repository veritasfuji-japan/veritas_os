"""Tests for scripts/reset_repo_runtime.py."""

from __future__ import annotations

from pathlib import Path

from scripts import reset_repo_runtime


def test_iter_targets_finds_runtime_artifacts(tmp_path, monkeypatch):
    """Runtime artifacts are detected while .gitkeep is preserved."""
    repo_root = tmp_path
    runtime_dev = repo_root / "runtime" / "dev"
    runtime_dev.mkdir(parents=True)
    (runtime_dev / ".gitkeep").write_text("", encoding="utf-8")
    junk = runtime_dev / "trust_log.jsonl"
    junk.write_text('{"x": 1}\n', encoding="utf-8")

    monkeypatch.setattr(reset_repo_runtime, "REPO_ROOT", repo_root)
    targets = reset_repo_runtime._iter_deletion_targets()

    assert junk.resolve() in targets
    assert (runtime_dev / ".gitkeep").resolve() not in targets


def test_apply_keeps_runtime_gitkeep(tmp_path, monkeypatch):
    """--apply style deletion removes files and recreates .gitkeep placeholders."""
    repo_root = tmp_path
    runtime_dev = repo_root / "runtime" / "dev"
    runtime_prod = repo_root / "runtime" / "prod"
    runtime_dev.mkdir(parents=True)
    runtime_prod.mkdir(parents=True)
    (runtime_dev / "world_state.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(reset_repo_runtime, "REPO_ROOT", repo_root)

    targets = reset_repo_runtime._iter_deletion_targets()
    reset_repo_runtime._delete_paths(targets, apply=True)
    reset_repo_runtime._ensure_gitkeep()

    assert not (runtime_dev / "world_state.json").exists()
    assert (runtime_dev / ".gitkeep").exists()
    assert (runtime_prod / ".gitkeep").exists()


def test_dry_run_does_not_delete(tmp_path, monkeypatch):
    """Dry-run mode reports paths without deleting files."""
    repo_root = tmp_path
    logs_dir = repo_root / "logs"
    logs_dir.mkdir(parents=True)
    log_file = logs_dir / "app.log"
    log_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(reset_repo_runtime, "REPO_ROOT", repo_root)

    targets = reset_repo_runtime._iter_deletion_targets()
    reset_repo_runtime._delete_paths(targets, apply=False)

    assert log_file.exists()


def test_iter_targets_does_not_touch_sample_fixture(tmp_path, monkeypatch):
    """Sample fixture paths outside runtime roots are not cleanup targets."""
    repo_root = tmp_path
    sample_file = repo_root / "veritas_os" / "sample_data" / "memory" / "episodic.sample.jsonl"
    sample_file.parent.mkdir(parents=True)
    sample_file.write_text('{"id": "sample"}\n', encoding="utf-8")

    monkeypatch.setattr(reset_repo_runtime, "REPO_ROOT", repo_root)

    targets = reset_repo_runtime._iter_deletion_targets()
    assert sample_file.resolve() not in targets
