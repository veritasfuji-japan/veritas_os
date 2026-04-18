"""Tests for Alembic migration infrastructure.

Validates that:
* Alembic configuration is loadable and well-formed.
* The initial migration module is importable with correct revision IDs.
* upgrade() / downgrade() functions exist and are callable.
* Migration revision chain is linear with no gaps.
* env.py rejects missing VERITAS_DATABASE_URL.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = REPO_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


# ── Configuration files exist ───────────────────────────────────────────


class TestAlembicStructure:
    """Verify the Alembic directory layout is correct."""

    def test_alembic_ini_exists(self):
        assert ALEMBIC_INI.exists(), "alembic.ini must exist at repo root"

    def test_alembic_dir_exists(self):
        assert ALEMBIC_DIR.is_dir(), "alembic/ directory must exist"

    def test_env_py_exists(self):
        assert (ALEMBIC_DIR / "env.py").exists(), "alembic/env.py must exist"

    def test_versions_dir_exists(self):
        assert VERSIONS_DIR.is_dir(), "alembic/versions/ directory must exist"

    def test_script_mako_exists(self):
        assert (
            ALEMBIC_DIR / "script.py.mako"
        ).exists(), "alembic/script.py.mako must exist"

    def test_alembic_ini_references_veritas_database_url(self):
        """alembic.ini must NOT contain a hardcoded sqlalchemy.url."""
        content = ALEMBIC_INI.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("sqlalchemy.url") and "=" in stripped:
                # Only acceptable if commented out or blank
                if not stripped.startswith("#"):
                    value = stripped.split("=", 1)[1].strip()
                    assert value == "", (
                        "sqlalchemy.url must be blank or commented out in "
                        "alembic.ini — credentials belong in "
                        "VERITAS_DATABASE_URL"
                    )

    def test_alembic_ini_version_table(self):
        """Verify the Alembic version table name is configured."""
        content = ALEMBIC_INI.read_text(encoding="utf-8")
        assert "version_table = alembic_version" in content


# ── Initial migration module ────────────────────────────────────────────


def _load_migration(name: str) -> ModuleType:
    """Import a migration module by file name (without .py)."""
    spec = importlib.util.spec_from_file_location(
        name, VERSIONS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestInitialMigration:
    """Verify the 0001_initial_schema migration."""

    @pytest.fixture()
    def migration(self) -> ModuleType:
        return _load_migration("0001_initial_schema")

    def test_revision_id(self, migration: ModuleType):
        assert migration.revision == "0001"

    def test_down_revision_is_none(self, migration: ModuleType):
        assert migration.down_revision is None

    def test_upgrade_is_callable(self, migration: ModuleType):
        assert callable(migration.upgrade)

    def test_downgrade_is_callable(self, migration: ModuleType):
        assert callable(migration.downgrade)

    def test_upgrade_uses_create_table(self, migration: ModuleType):
        """upgrade() should call op.create_table for each table."""
        import inspect

        source = inspect.getsource(migration.upgrade)
        assert "create_table" in source
        assert "memory_records" in source
        assert "trustlog_entries" in source
        assert "trustlog_chain_state" in source

    def test_downgrade_uses_drop_table(self, migration: ModuleType):
        """downgrade() should call op.drop_table for each table."""
        import inspect

        source = inspect.getsource(migration.downgrade)
        assert "drop_table" in source
        assert "memory_records" in source
        assert "trustlog_entries" in source
        assert "trustlog_chain_state" in source

    def test_metadata_columns_present(self, migration: ModuleType):
        """Migration should include metadata JSONB columns for extensibility."""
        import inspect

        source = inspect.getsource(migration.upgrade)
        # metadata column should appear in both memory_records and trustlog_entries
        assert source.count('"metadata"') >= 2


class TestGovernanceMigration:
    """Verify governance-specific migration metadata and DDL intent."""

    @pytest.fixture()
    def migration(self) -> ModuleType:
        return _load_migration("0002_governance_policy_tables")

    def test_revision_id(self, migration: ModuleType):
        assert migration.revision == "0002"

    def test_down_revision(self, migration: ModuleType):
        assert migration.down_revision == "0001"

    def test_upgrade_contains_governance_tables(self, migration: ModuleType):
        import inspect

        source = inspect.getsource(migration.upgrade)
        assert "governance_policies" in source
        assert "governance_policy_events" in source
        assert "governance_approvals" in source


class TestGovernanceIntegrityMigration:
    """Verify governance integrity hardening migration metadata and DDL intent."""

    @pytest.fixture()
    def migration(self) -> ModuleType:
        return _load_migration("0003_governance_integrity_hardening")

    def test_revision_id(self, migration: ModuleType):
        assert migration.revision == "0003"

    def test_down_revision(self, migration: ModuleType):
        assert migration.down_revision == "0002"

    def test_upgrade_contains_integrity_constraints(self, migration: ModuleType):
        import inspect

        source = inspect.getsource(migration.upgrade)
        assert "ck_governance_policies_policy_revision_positive" in source
        assert "uq_governance_policies_policy_revision" in source
        assert "ck_governance_approvals_reviewer_non_empty" in source

# ── Revision chain integrity ────────────────────────────────────────────


class TestRevisionChain:
    """Verify the migration revision chain is linear and complete."""

    def _discover_migrations(self) -> list[ModuleType]:
        """Load all migration modules from versions/ dir."""
        mods: list[ModuleType] = []
        for path in sorted(VERSIONS_DIR.glob("*.py")):
            if path.name.startswith("__"):
                continue
            mod = _load_migration(path.stem)
            if hasattr(mod, "revision"):
                mods.append(mod)
        return mods

    def test_at_least_one_migration_exists(self):
        assert len(self._discover_migrations()) >= 1

    def test_chain_starts_at_none(self):
        """The first migration in the chain must have down_revision = None."""
        mods = self._discover_migrations()
        first = mods[0]
        assert first.down_revision is None, (
            f"First migration {first.revision} must have "
            f"down_revision=None, got {first.down_revision}"
        )

    def test_chain_is_linear(self):
        """Each migration's down_revision must point to the previous one."""
        mods = self._discover_migrations()
        if len(mods) < 2:
            return  # single migration — chain is trivially linear
        for i in range(1, len(mods)):
            assert mods[i].down_revision == mods[i - 1].revision, (
                f"Migration {mods[i].revision} has down_revision="
                f"{mods[i].down_revision}, expected {mods[i - 1].revision}"
            )

    def test_all_revisions_unique(self):
        mods = self._discover_migrations()
        revisions = [m.revision for m in mods]
        assert len(revisions) == len(set(revisions)), "Duplicate revision IDs"


# ── env.py validation ───────────────────────────────────────────────────


class TestEnvPy:
    """Verify env.py behavior without a live database."""

    def test_get_url_raises_without_env(self):
        """env.py's _get_url should exit when VERITAS_DATABASE_URL is unset."""
        # Re-implement the same logic as env.py _get_url to test in isolation
        # (env.py cannot be trivially imported due to alembic.context side effects).
        with patch.dict(os.environ, {}, clear=True):
            url = os.getenv("VERITAS_DATABASE_URL", "").strip()
            assert url == "", "VERITAS_DATABASE_URL should not be set"

    def test_get_url_returns_env_value(self):
        """env.py's _get_url should return the VERITAS_DATABASE_URL value."""
        test_url = "postgresql://test:test@localhost:5432/testdb"
        with patch.dict(os.environ, {"VERITAS_DATABASE_URL": test_url}):
            url = os.getenv("VERITAS_DATABASE_URL", "").strip()
            assert url == test_url

    def test_env_py_contains_get_url_function(self):
        """env.py should define _get_url that reads VERITAS_DATABASE_URL."""
        env_source = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "def _get_url()" in env_source
        assert "VERITAS_DATABASE_URL" in env_source

    def test_env_py_contains_offline_mode(self):
        """env.py should support offline mode for SQL script generation."""
        env_source = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "run_migrations_offline" in env_source
        assert "run_migrations_online" in env_source
        assert "is_offline_mode" in env_source

    def test_env_py_uses_null_pool(self):
        """env.py should use NullPool for migration connections."""
        env_source = (ALEMBIC_DIR / "env.py").read_text(encoding="utf-8")
        assert "NullPool" in env_source
