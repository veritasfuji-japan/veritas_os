"""Tests for scripts.security.check_runtime_pickle_artifacts."""

from __future__ import annotations

from pathlib import Path

from scripts.security import check_runtime_pickle_artifacts as checker


def test_find_legacy_pickles_recursive_and_case_insensitive(tmp_path: Path) -> None:
    """Nested and mixed-case legacy artifact files are detected."""
    direct = tmp_path / "legacy.pkl"
    direct.write_bytes(b"legacy")

    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested = nested_dir / "detected.pkl"
    nested.write_bytes(b"legacy")

    upper = tmp_path / "MODEL.PKL"
    upper.write_bytes(b"legacy")

    joblib = tmp_path / "embedder.joblib"
    joblib.write_bytes(b"legacy")

    upper_joblib = tmp_path / "INDEX.JOBLIB"
    upper_joblib.write_bytes(b"legacy")

    findings = checker._find_legacy_pickles([tmp_path])

    assert findings == [upper_joblib, upper, joblib, direct, nested]


def test_main_returns_error_when_findings_exist(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """`main` returns non-zero and prints security warning on detection."""
    legacy = tmp_path / "artifact.pkl"
    legacy.write_bytes(b"legacy")

    monkeypatch.setattr(checker, "DEFAULT_SCAN_DIRS", [])
    exit_code = checker.main(["--scan-dir", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "[SECURITY] Legacy runtime pickle artifacts detected" in output
    assert "artifact.pkl" in output


def test_main_returns_success_when_no_findings(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """`main` returns zero when scan targets are clean."""
    clean_file = tmp_path / "artifact.json"
    clean_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(checker, "DEFAULT_SCAN_DIRS", [])
    exit_code = checker.main(["--scan-dir", str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No legacy runtime pickle artifacts detected" in output
