"""Tests for scripts.security.check_subprocess_shell_usage."""

from __future__ import annotations

from pathlib import Path

from scripts.security import check_subprocess_shell_usage as checker


def test_scan_file_detects_shell_true_and_string_command(tmp_path: Path) -> None:
    """Scanner should flag shell=True and direct string command usage."""
    source = tmp_path / "bad.py"
    source.write_text(
        "\n".join(
            [
                "import subprocess",
                "subprocess.run('echo hi', shell=True)",
            ]
        ),
        encoding="utf-8",
    )

    violations = checker._scan_file(source)

    assert len(violations) == 2
    assert any("shell=True" in violation.message for violation in violations)
    assert any("string command" in violation.message for violation in violations)


def test_scan_file_allows_list_command_without_shell(tmp_path: Path) -> None:
    """List-form command without shell=True should not be flagged."""
    source = tmp_path / "good.py"
    source.write_text(
        "\n".join(
            [
                "import subprocess",
                "subprocess.run(['echo', 'hi'], check=True)",
            ]
        ),
        encoding="utf-8",
    )

    violations = checker._scan_file(source)

    assert violations == []


def test_scan_file_allows_string_command_with_explicit_marker(tmp_path: Path) -> None:
    """Marker comment should permit documented string command exceptions."""
    source = tmp_path / "allow.py"
    source.write_text(
        "\n".join(
            [
                "# allow-subprocess-string-command",
                "import subprocess",
                "subprocess.run('git rev-parse --short HEAD', check=True)",
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
    """Command exits with 1 and prints remediation guidance on violations."""
    source = tmp_path / "bad.py"
    source.write_text(
        "import subprocess\nsubprocess.run('echo hi', shell=True)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Risky subprocess usage detected" in output
    assert "Security remediation" in output


def test_main_returns_zero_when_clean(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    """Command exits with 0 and prints success output on clean code."""
    source = tmp_path / "good.py"
    source.write_text(
        "import subprocess\nsubprocess.run(['echo', 'hi'], check=True)\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No risky subprocess usage detected" in output


def test_iter_python_files_skips_tests_directory(tmp_path: Path) -> None:
    """File iterator should skip test directories to reduce false positives."""
    app_dir = tmp_path / "veritas_os"
    tests_dir = app_dir / "tests"
    app_dir.mkdir()
    tests_dir.mkdir()

    prod_file = app_dir / "runner.py"
    test_file = tests_dir / "test_runner.py"
    prod_file.write_text("print('ok')\n", encoding="utf-8")
    test_file.write_text("print('test')\n", encoding="utf-8")

    files = checker._iter_python_files([app_dir])

    assert prod_file.resolve() in files
    assert test_file.resolve() not in files
