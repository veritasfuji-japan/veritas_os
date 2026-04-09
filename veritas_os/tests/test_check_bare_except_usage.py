"""Tests for scripts.security.check_bare_except_usage."""

from __future__ import annotations

from pathlib import Path

from scripts.security import check_bare_except_usage as checker


def test_scan_file_detects_bare_except(tmp_path: Path) -> None:
    """Scanner should flag bare ``except:`` handlers."""
    source = tmp_path / "bad.py"
    source.write_text(
        "\n".join(
            [
                "def run():",
                "    try:",
                "        return 1",
                "    except:",
                "        return 0",
            ]
        ),
        encoding="utf-8",
    )

    violations = checker._scan_file(source)

    assert len(violations) == 1
    assert "bare except" in violations[0].message


def test_scan_file_allows_explicit_exception(tmp_path: Path) -> None:
    """Scanner should allow explicit exception classes."""
    source = tmp_path / "good.py"
    source.write_text(
        "\n".join(
            [
                "def run():",
                "    try:",
                "        return int('x')",
                "    except ValueError:",
                "        return None",
            ]
        ),
        encoding="utf-8",
    )

    violations = checker._scan_file(source)

    assert violations == []


def test_main_returns_non_zero_when_violation_found(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    """Command should fail and print remediation guidance on violations."""
    source = tmp_path / "bad.py"
    source.write_text("try:\n    pass\nexcept:\n    pass\n", encoding="utf-8")

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Bare except usage detected" in output
    assert "Security remediation" in output


def test_main_returns_zero_when_clean(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    """Command should succeed and print clean-status output."""
    source = tmp_path / "good.py"
    source.write_text("value = 1\n", encoding="utf-8")

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No bare except usage detected" in output


def test_iter_python_files_skips_tests_directory(tmp_path: Path) -> None:
    """File iterator should skip test directories to reduce false positives."""
    app_dir = tmp_path / "veritas_os"
    tests_dir = app_dir / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()

    prod_file = app_dir / "runtime.py"
    test_file = tests_dir / "test_runtime.py"
    prod_file.write_text("print('ok')\n", encoding="utf-8")
    test_file.write_text("print('test')\n", encoding="utf-8")

    files = checker._iter_python_files([app_dir])

    assert prod_file.resolve() in files
    assert test_file.resolve() not in files
