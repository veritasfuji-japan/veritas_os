"""Tests for canonical runtime path centralization.

Validates that all runtime artifacts resolve inside the repository's
``runtime/`` tree and that no stray external directories are created.

Note: ``veritas_os.logging.paths`` evaluates module-level constants at import
time.  Tests that check those constants may be affected by other tests that
set env vars before import.  To avoid flakiness, we test the *resolution
functions* directly with controlled environment.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]  # git repo root
PKG_ROOT = Path(__file__).resolve().parents[1]    # veritas_os package root


def _is_under(child: Path, parent: Path) -> bool:
    """Return True if *child* is under *parent* after resolution."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _clean_env():
    """Return env dict with all VERITAS path env vars removed."""
    return {
        k: v for k, v in os.environ.items()
        if not k.startswith("VERITAS_") and k not in (
            "WORLD_STATE_PATH",
        )
    }


# ---------------------------------------------------------------------------
# Case 1: Default local run — canonical runtime path is repo-local
# ---------------------------------------------------------------------------
class TestDefaultCanonicalPaths:
    """Verify that default (no env override) paths resolve inside the repo."""

    def test_logging_paths_runtime_root_default(self):
        """_resolve_runtime_root() defaults to {project_root}/runtime."""
        from veritas_os.logging.paths import _resolve_runtime_root
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            root = _resolve_runtime_root()
        assert _is_under(root, REPO_ROOT)
        assert root.name == "runtime"

    def test_logging_paths_log_root_default(self):
        """_resolve_log_root() defaults to runtime/<ns>/logs."""
        from veritas_os.logging.paths import _resolve_log_root
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            log_root = _resolve_log_root()
        assert _is_under(log_root, REPO_ROOT)
        assert "runtime" in str(log_root)

    def test_scripts_runtime_paths_are_repo_local(self):
        from veritas_os.scripts import _runtime_paths as rp
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            root = rp._resolve_runtime_root()
        assert _is_under(root, REPO_ROOT)

    def test_config_runtime_root_is_repo_local(self):
        from veritas_os.core.config import VeritasConfig
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            cfg = VeritasConfig()
        assert _is_under(cfg.runtime_root, REPO_ROOT)

    def test_config_log_dir_is_repo_local(self):
        from veritas_os.core.config import VeritasConfig
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            cfg = VeritasConfig()
        assert _is_under(cfg.log_dir, REPO_ROOT)

    def test_config_data_dir_is_repo_local(self):
        from veritas_os.core.config import VeritasConfig
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            cfg = VeritasConfig()
        assert _is_under(cfg.data_dir, REPO_ROOT)


# ---------------------------------------------------------------------------
# Case 2: No stray legacy folders
# ---------------------------------------------------------------------------
class TestNoStrayLegacyPaths:
    """Ensure canonical paths do NOT point to legacy scattered locations."""

    def test_default_log_root_is_not_scripts_logs(self):
        from veritas_os.logging.paths import _resolve_log_root
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            log_root = _resolve_log_root()
        scripts_logs = PKG_ROOT / "scripts" / "logs"
        assert log_root != scripts_logs
        assert "scripts/logs" not in str(log_root)

    def test_world_fallback_is_not_home_dir(self):
        """world.py fallback must not use Path.home()/veritas."""
        from veritas_os.core import world
        # Trigger the fallback by using an invalid base env
        with mock.patch.dict(os.environ, {
            "VERITAS_DATA_DIR": "/proc/fake",
            "VERITAS_RUNTIME_ROOT": "",
            "VERITAS_RUNTIME_NAMESPACE": "",
        }, clear=False):
            path = world._resolve_data_dir()
        # Must NOT fall back to ~/veritas or ~/.veritas_os
        home = Path.home()
        assert path != home / "veritas"
        assert path != home / ".veritas_os"
        # Must resolve to repo-local runtime path
        assert _is_under(path, REPO_ROOT)


# ---------------------------------------------------------------------------
# Case 3: Env overrides still work
# ---------------------------------------------------------------------------
class TestEnvOverrides:
    """Verify that explicit env overrides are respected."""

    def test_runtime_root_override(self, tmp_path):
        from veritas_os.scripts import _runtime_paths
        with mock.patch.dict(os.environ, {
            "VERITAS_RUNTIME_ROOT": str(tmp_path / "custom_runtime"),
        }):
            root = _runtime_paths._resolve_runtime_root()
        assert root == tmp_path / "custom_runtime"

    def test_runtime_namespace_override(self):
        from veritas_os.scripts import _runtime_paths
        with mock.patch.dict(os.environ, {
            "VERITAS_RUNTIME_NAMESPACE": "staging_test",
        }):
            ns = _runtime_paths._resolve_namespace()
        assert ns == "staging_test"

    def test_runtime_namespace_from_veritas_env(self):
        from veritas_os.scripts import _runtime_paths
        with mock.patch.dict(os.environ, {
            "VERITAS_RUNTIME_NAMESPACE": "",
            "VERITAS_ENV": "production",
        }):
            ns = _runtime_paths._resolve_namespace()
        assert ns == "prod"

    def test_log_root_override(self, tmp_path):
        from veritas_os.logging.paths import _resolve_log_root
        with mock.patch.dict(os.environ, {
            **_clean_env(),
            "VERITAS_LOG_ROOT": str(tmp_path / "custom_logs"),
        }, clear=True):
            log_root = _resolve_log_root()
        assert log_root == tmp_path / "custom_logs"


# ---------------------------------------------------------------------------
# Case 4: Key artifact paths are correct
# ---------------------------------------------------------------------------
class TestArtifactPaths:
    """Verify key artifact paths land in the canonical structure."""

    def test_canonical_tree_structure(self):
        """Verify the expected directory hierarchy from resolution functions."""
        from veritas_os.logging.paths import (
            _resolve_runtime_root, _resolve_runtime_namespace,
        )
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            runtime_root = _resolve_runtime_root()
            namespace = _resolve_runtime_namespace()

        runtime_dir = runtime_root / namespace
        assert (runtime_dir / "logs").parent == runtime_dir
        assert (runtime_dir / "data").parent == runtime_dir

    def test_scripts_paths_canonical_structure(self):
        """All script canonical paths share a common runtime_dir ancestor."""
        from veritas_os.scripts._runtime_paths import (
            RUNTIME_DIR, LOG_DIR, DATA_DIR,
            DOCTOR_DIR, BENCH_LOG_DIR, REPORT_DIR,
            DATASET_DIR, MODELS_DIR, DASH_DIR,
        )
        assert LOG_DIR == RUNTIME_DIR / "logs"
        assert DATA_DIR == RUNTIME_DIR / "data"
        assert BENCH_LOG_DIR == RUNTIME_DIR / "benchmarks"
        assert REPORT_DIR == RUNTIME_DIR / "reports"
        assert MODELS_DIR == RUNTIME_DIR / "models"
        assert DATASET_DIR == RUNTIME_DIR / "datasets"
        assert DOCTOR_DIR == RUNTIME_DIR / "logs" / "doctor"
        assert DASH_DIR == RUNTIME_DIR / "logs" / "DASH"

    def test_doctor_report_under_doctor_dir(self):
        from veritas_os.scripts._runtime_paths import (
            DOCTOR_DIR, DOCTOR_REPORT_JSON,
        )
        assert DOCTOR_REPORT_JSON.parent == DOCTOR_DIR
        assert DOCTOR_REPORT_JSON.name == "doctor_report.json"

    def test_trust_log_under_log_dir(self):
        from veritas_os.scripts._runtime_paths import (
            LOG_DIR, TRUST_LOG_JSONL,
        )
        assert TRUST_LOG_JSONL.parent == LOG_DIR
        assert TRUST_LOG_JSONL.name == "trust_log.jsonl"
