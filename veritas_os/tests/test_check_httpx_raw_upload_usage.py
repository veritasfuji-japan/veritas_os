"""Tests for scripts.security.check_httpx_raw_upload_usage."""

from __future__ import annotations

from pathlib import Path

from scripts.security import check_httpx_raw_upload_usage as checker


def test_scan_file_detects_data_with_bytes_or_string(tmp_path: Path) -> None:
    """The scanner flags obvious deprecated raw payload usage in data=."""
    source = tmp_path / "sample.py"
    source.write_text(
        "\n".join(
            [
                "import httpx",
                "httpx.post('https://x.example', data='hello')",
                "httpx.put('https://x.example', data=b'hello')",
                "httpx.patch('https://x.example', content='safe')",
            ]
        ),
        encoding="utf-8",
    )

    violations = checker._scan_file(source)

    assert len(violations) == 2
    assert violations[0].line == 2
    assert violations[1].line == 3


def test_scan_file_ignores_non_raw_data_literal(tmp_path: Path) -> None:
    """Form-like data payloads are not flagged by this guard."""
    source = tmp_path / "sample.py"
    source.write_text(
        "\n".join(
            [
                "import httpx",
                "httpx.post('https://x.example', data={'k': 'v'})",
                "httpx.post('https://x.example', files={'f': b'1'})",
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
    """The command returns 1 and prints remediation guidance on violations."""
    source = tmp_path / "bad.py"
    source.write_text(
        "import httpx\nhttpx.post('https://x.example', data='raw')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Deprecated httpx raw upload usage detected" in output
    assert "use content=" in output


def test_main_returns_zero_when_clean(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    """The command returns 0 when no deprecated usage is found."""
    source = tmp_path / "good.py"
    source.write_text(
        "import httpx\nhttpx.post('https://x.example', content='raw')\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(checker, "DEFAULT_SCAN_ROOTS", ())
    exit_code = checker.main(["--scan-root", str(source)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "No deprecated httpx raw upload usage detected" in output
