"""Smoke tests for PostgreSQL backup / restore / recovery drill scripts.

These tests verify that the shell scripts exist, are executable, have valid
bash syntax, and print correct help / usage messages.  They do NOT require a
running PostgreSQL instance.

Markers:
    smoke — included in ``make test-smoke``
    unit  — standard unit test
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {
    "backup": REPO_ROOT / "scripts" / "backup_postgres.sh",
    "restore": REPO_ROOT / "scripts" / "restore_postgres.sh",
    "drill": REPO_ROOT / "scripts" / "drill_postgres_recovery.sh",
}


# ── Existence & permission tests ──────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.unit
class TestScriptExistence:
    """Verify scripts exist and have correct permissions."""

    @pytest.mark.parametrize("name,path", list(SCRIPTS.items()))
    def test_script_exists(self, name: str, path: Path) -> None:
        assert path.exists(), f"{name} script not found at {path}"

    @pytest.mark.parametrize("name,path", list(SCRIPTS.items()))
    def test_script_is_executable(self, name: str, path: Path) -> None:
        assert os.access(path, os.X_OK), f"{name} script is not executable"

    @pytest.mark.parametrize("name,path", list(SCRIPTS.items()))
    def test_script_has_shebang(self, name: str, path: Path) -> None:
        first_line = path.read_text().split("\n")[0]
        assert first_line.startswith("#!/"), (
            f"{name} script missing shebang line"
        )


# ── Bash syntax check ────────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.unit
class TestScriptSyntax:
    """Validate bash syntax without executing scripts."""

    @pytest.mark.parametrize("name,path", list(SCRIPTS.items()))
    def test_bash_syntax_valid(self, name: str, path: Path) -> None:
        result = subprocess.run(
            ["bash", "-n", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"{name} script has bash syntax errors:\n{result.stderr}"
        )


# ── Help / usage output ──────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.unit
class TestScriptHelp:
    """Verify --help flag produces usage output and exits 0."""

    @pytest.mark.parametrize("name,path", list(SCRIPTS.items()))
    def test_help_flag(self, name: str, path: Path) -> None:
        result = subprocess.run(
            ["bash", str(path), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"{name} --help returned non-zero: {result.stderr}"
        )
        assert "usage" in result.stdout.lower() or "Usage" in result.stdout, (
            f"{name} --help output does not contain usage information"
        )


# ── Script content coherence ─────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.unit
class TestScriptContent:
    """Verify scripts reference expected tools and patterns."""

    def test_backup_uses_pg_dump(self) -> None:
        content = SCRIPTS["backup"].read_text()
        assert "pg_dump" in content

    def test_restore_uses_pg_restore(self) -> None:
        content = SCRIPTS["restore"].read_text()
        assert "pg_restore" in content

    def test_drill_calls_backup_and_restore(self) -> None:
        content = SCRIPTS["drill"].read_text()
        assert "backup_postgres.sh" in content
        assert "restore_postgres.sh" in content

    def test_drill_checks_trustlog_chain(self) -> None:
        content = SCRIPTS["drill"].read_text()
        assert "trustlog_entries" in content
        assert "trustlog_chain_state" in content

    def test_restore_checks_chain_state(self) -> None:
        content = SCRIPTS["restore"].read_text()
        assert "trustlog_chain_state" in content

    def test_drill_has_health_check(self) -> None:
        content = SCRIPTS["drill"].read_text()
        assert "/health" in content

    def test_backup_supports_veritas_database_url(self) -> None:
        content = SCRIPTS["backup"].read_text()
        assert "VERITAS_DATABASE_URL" in content

    def test_restore_supports_verify_flag(self) -> None:
        content = SCRIPTS["restore"].read_text()
        assert "--verify" in content

    def test_drill_supports_ci_flag(self) -> None:
        content = SCRIPTS["drill"].read_text()
        assert "--ci" in content


# ── Runbook coherence ────────────────────────────────────────────────────


@pytest.mark.smoke
@pytest.mark.unit
class TestRunbookCoherence:
    """Verify the drill runbook references all scripts and key concepts."""

    RUNBOOK = REPO_ROOT / "docs" / "postgresql-drill-runbook.md"

    def test_runbook_exists(self) -> None:
        assert self.RUNBOOK.exists(), "postgresql-drill-runbook.md not found"

    def test_runbook_references_all_scripts(self) -> None:
        content = self.RUNBOOK.read_text()
        for script_name in [
            "backup_postgres.sh",
            "restore_postgres.sh",
            "drill_postgres_recovery.sh",
        ]:
            assert script_name in content, (
                f"Runbook does not reference {script_name}"
            )

    def test_runbook_documents_safe_unsafe_boundaries(self) -> None:
        content = self.RUNBOOK.read_text()
        assert "safe" in content.lower()
        assert "unsafe" in content.lower() or "not safe" in content.lower()

    def test_runbook_documents_single_primary(self) -> None:
        content = self.RUNBOOK.read_text()
        assert "single writable primary" in content.lower() or \
               "single" in content.lower()

    def test_runbook_documents_advisory_lock(self) -> None:
        content = self.RUNBOOK.read_text()
        assert "advisory" in content.lower()

    def test_runbook_documents_exit_codes(self) -> None:
        content = self.RUNBOOK.read_text()
        assert "exit code" in content.lower() or "Exit code" in content

    def test_runbook_links_to_production_guide(self) -> None:
        content = self.RUNBOOK.read_text()
        assert "postgresql-production-guide" in content
