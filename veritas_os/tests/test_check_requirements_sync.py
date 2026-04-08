"""Tests for scripts.quality.check_requirements_sync."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import check_requirements_sync as checker


def test_extract_dependency_name_normalizes_extras_and_markers() -> None:
    """Dependency parser should normalize package names deterministically."""
    assert checker.extract_dependency_name("Foo_Bar[baz]>=1.2; python_version<'3.13'") == "foo-bar"


def test_expected_dependency_names_expands_full_extra_closure() -> None:
    """Expected set should include nested extras referenced by ``full``."""
    pyproject_data = {
        "project": {
            "dependencies": ["alpha==1.0"],
            "optional-dependencies": {
                "ml": ["beta==2.0"],
                "ops": ["gamma>=3.0"],
                "full": ["veritas-os[ml,ops]"],
            },
        }
    }

    expected = checker.expected_dependency_names(pyproject_data)

    assert expected == {"alpha", "beta", "gamma"}


def test_main_returns_success_for_current_repository_manifests(capsys) -> None:
    """Current repository dependency manifests should remain synchronized."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Dependency manifests are in sync" in output


def test_ci_and_makefile_include_requirements_sync_guard() -> None:
    """CI and local quality checks should enforce requirements sync guard."""
    root = Path(__file__).resolve().parents[2]
    workflow_content = (root / ".github" / "workflows" / "main.yml").read_text(
        encoding="utf-8",
    )
    makefile_content = (root / "Makefile").read_text(encoding="utf-8")

    assert "python scripts/quality/check_requirements_sync.py" in workflow_content
    assert "python scripts/quality/check_requirements_sync.py" in makefile_content
