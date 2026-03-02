"""Tests for static responsibility boundary checker script."""

from __future__ import annotations

from pathlib import Path

from scripts.architecture.check_responsibility_boundaries import (
    BoundaryRule,
    check_boundaries,
)


def _write_module(path: Path, source: str) -> None:
    """Write UTF-8 source code to a module path."""
    path.write_text(source, encoding="utf-8")


def test_check_boundaries_reports_forbidden_import(tmp_path: Path) -> None:
    """Checker should report violations when forbidden imports exist."""
    _write_module(tmp_path / "planner.py", "import veritas_os.core.kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert len(issues) == 1
    assert "planner" in issues[0]
    assert "kernel" in issues[0]


def test_check_boundaries_accepts_valid_dependency_directions(tmp_path: Path) -> None:
    """Checker should pass when no forbidden cross-module imports are present."""
    _write_module(tmp_path / "planner.py", "from veritas_os.core.memory import summarize_for_planner\n")
    _write_module(tmp_path / "kernel.py", "from veritas_os.core.planner import plan_for_veritas_agi\n")
    _write_module(tmp_path / "fuji.py", "from veritas_os.core.fuji_codes import FujiAction\n")
    _write_module(tmp_path / "memory.py", "import json\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert issues == []


def test_check_boundaries_supports_custom_rules(tmp_path: Path) -> None:
    """Checker should evaluate custom rules provided by callers."""
    _write_module(tmp_path / "kernel.py", "from veritas_os.core.memory import add\n")
    _write_module(tmp_path / "planner.py", "# planner module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(
        core_dir=tmp_path,
        rules=(
            BoundaryRule(
                source_module="kernel",
                forbidden_imports=frozenset({"memory"}),
            ),
        ),
    )

    assert len(issues) == 1
    assert "kernel" in issues[0]
    assert "memory" in issues[0]
