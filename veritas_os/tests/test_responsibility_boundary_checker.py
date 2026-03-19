"""Tests for static responsibility boundary checker script."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.architecture.check_responsibility_boundaries import (
    REMEDIATION_LINK,
    BoundaryIssue,
    BoundaryRule,
    ViolationDetail,
    build_machine_report,
    build_remediation_guide,
    check_boundaries,
    collect_boundary_issues,
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


def test_check_boundaries_detects_from_core_import_pattern(tmp_path: Path) -> None:
    """Checker should catch `from veritas_os.core import <forbidden>` imports."""
    _write_module(tmp_path / "planner.py", "from veritas_os.core import kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = check_boundaries(core_dir=tmp_path)

    assert len(issues) == 1
    assert "planner" in issues[0]
    assert "kernel" in issues[0]


def test_build_remediation_guide_contains_required_columns(tmp_path: Path) -> None:
    """Remediation guide should include forbidden dependency, alternatives, and link."""
    violations = [
        ViolationDetail(
            source_module="planner",
            forbidden_module="kernel",
            path=tmp_path / "planner.py",
        ),
    ]

    guide = build_remediation_guide(violations)

    assert "禁止依存" in guide
    assert "代替実装先（許可依存）" in guide
    assert "正規拡張ポイント" in guide
    assert "planner -> kernel" in guide
    assert "veritas_os.core.memory" in guide
    assert "veritas_os.core.planner_normalization" in guide
    assert REMEDIATION_LINK in guide


def test_build_remediation_guide_returns_empty_for_no_violations() -> None:
    """No remediation guide should be emitted when violations are absent."""
    guide = build_remediation_guide([])

    assert guide == ""


def test_collect_boundary_issues_classifies_missing_module(tmp_path: Path) -> None:
    """Missing source modules should be classified as input_invalid."""
    _write_module(tmp_path / "planner.py", "# planner module\n")

    issues = collect_boundary_issues(core_dir=tmp_path)

    assert any(issue.code == "input_invalid" for issue in issues)


def test_collect_boundary_issues_classifies_boundary_violation(tmp_path: Path) -> None:
    """Forbidden import should be classified as boundary_violation."""
    _write_module(tmp_path / "planner.py", "import veritas_os.core.kernel\n")
    _write_module(tmp_path / "kernel.py", "# kernel module\n")
    _write_module(tmp_path / "fuji.py", "# fuji module\n")
    _write_module(tmp_path / "memory.py", "# memory module\n")

    issues = collect_boundary_issues(core_dir=tmp_path)

    assert len(issues) == 1
    assert issues[0].code == "boundary_violation"
    assert issues[0].source_module == "planner"
    assert issues[0].forbidden_module == "kernel"


def test_build_machine_report_counts_by_code(tmp_path: Path) -> None:
    """Machine report should summarize issue counts for CI parsers."""
    issues = [
        BoundaryIssue(
            code="boundary_violation",
            message="violation",
            path=tmp_path / "planner.py",
            source_module="planner",
            forbidden_module="kernel",
        ),
        BoundaryIssue(
            code="permission_denied",
            message="permission denied",
            path=tmp_path / "fuji.py",
            source_module="fuji",
        ),
    ]

    report = json.loads(build_machine_report(issues))

    assert report["status"] == "failed"
    assert report["summary"]["boundary_violation"] == 1
    assert report["summary"]["permission_denied"] == 1
    assert report["summary"]["input_invalid"] == 0
