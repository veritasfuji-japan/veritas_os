"""Tests for scripts.quality.check_frontend_docs_consistency."""

from __future__ import annotations

from pathlib import Path

from scripts.quality import check_frontend_docs_consistency as checker


def test_check_consistency_passes_when_versions_match() -> None:
    """No problems when README versions match package.json."""
    readme = (
        "| Framework | Next.js 16.1 (App Router) |\n"
        "| Language | TypeScript 5.7 |\n"
        "| Styling | Tailwind CSS 3.4 |\n"
        "| Lint Config | eslint-config-next 15.5 |\n"
    )
    pkg = {
        "dependencies": {"next": "16.1.7"},
        "devDependencies": {
            "typescript": "^5.7.2",
            "tailwindcss": "^3.4.17",
            "eslint-config-next": "15.5.10",
        },
    }
    problems = checker.check_consistency(readme, pkg)
    assert problems == []


def test_check_consistency_detects_nextjs_drift() -> None:
    """Should flag when README documents a different Next.js major.minor."""
    readme = (
        "| Framework | Next.js 15.5 (App Router) |\n"
        "| Language | TypeScript 5.7 |\n"
        "| Styling | Tailwind CSS 3.4 |\n"
        "| Lint Config | eslint-config-next 15.5 |\n"
    )
    pkg = {
        "dependencies": {"next": "16.1.7"},
        "devDependencies": {
            "typescript": "^5.7.2",
            "tailwindcss": "^3.4.17",
            "eslint-config-next": "15.5.10",
        },
    }
    problems = checker.check_consistency(readme, pkg)
    assert len(problems) == 1
    assert "next" in problems[0]
    assert "15.5" in problems[0]


def test_check_consistency_detects_eslint_config_next_drift() -> None:
    """Should flag when README documents different eslint-config-next major.minor."""
    readme = (
        "| Framework | Next.js 16.1 (App Router) |\n"
        "| Language | TypeScript 5.7 |\n"
        "| Styling | Tailwind CSS 3.4 |\n"
        "| Lint Config | eslint-config-next 16.2 |\n"
    )
    pkg = {
        "dependencies": {"next": "16.1.7"},
        "devDependencies": {
            "typescript": "^5.7.2",
            "tailwindcss": "^3.4.17",
            "eslint-config-next": "15.5.10",
        },
    }

    problems = checker.check_consistency(readme, pkg)

    assert len(problems) == 1
    assert "eslint-config-next" in problems[0]
    assert "16.2" in problems[0]


def test_check_consistency_detects_missing_dep() -> None:
    """Should flag when README documents a package not in package.json."""
    readme = (
        "| Framework | Next.js 16.1 (App Router) |\n"
        "| Language | TypeScript 5.7 |\n"
        "| Styling | Tailwind CSS 3.4 |\n"
        "| Lint Config | eslint-config-next 15.5 |\n"
    )
    pkg = {"dependencies": {}, "devDependencies": {}}
    problems = checker.check_consistency(readme, pkg)
    assert len(problems) == 4
    assert any("not in frontend/package.json" in p for p in problems)


def test_check_consistency_detects_missing_readme_mention() -> None:
    """Should flag when a version isn't mentioned in README at all."""
    readme = "No version info here."
    pkg = {
        "dependencies": {"next": "16.1.7"},
        "devDependencies": {
            "typescript": "^5.7.2",
            "tailwindcss": "^3.4.17",
            "eslint-config-next": "15.5.10",
        },
    }
    problems = checker.check_consistency(readme, pkg)
    assert len(problems) == 4
    assert any("does not mention" in p for p in problems)


def test_parse_major_minor_strips_caret() -> None:
    """Should parse major.minor from caret-prefixed semver."""
    assert checker._parse_major_minor("^5.7.2") == "5.7"
    assert checker._parse_major_minor("16.1.7") == "16.1"
    assert checker._parse_major_minor("^3.4.17") == "3.4"


def test_main_returns_success_for_current_repository(capsys) -> None:
    """Repository docs should satisfy the frontend consistency check."""
    exit_code = checker.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Frontend documentation consistency checks passed." in output


def test_ci_workflow_includes_frontend_docs_consistency_step() -> None:
    """CI lint workflow should include the frontend docs consistency check."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "main.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python scripts/quality/check_frontend_docs_consistency.py" in content
