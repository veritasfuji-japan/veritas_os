"""Tests for release evidence checksum writer."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

SCRIPT_RELATIVE_PATH = Path("scripts/release/write_release_evidence_checksums.py")
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / SCRIPT_RELATIVE_PATH
EXPECTED_ORDER = [
    "release-evidence-manifest.md",
    "release-evidence-reviewer-handoff.md",
    "staged-readiness-report.json",
    "staged-readiness-report.txt",
    "compose-validation-report.json",
    "live-provider-report.json",
]


def _run_script(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python", str(SCRIPT_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_output_lines(checksum_file: Path) -> list[tuple[str, str]]:
    lines = checksum_file.read_text(encoding="utf-8").splitlines()
    pairs: list[tuple[str, str]] = []
    for line in lines:
        checksum, rel_path = line.split("  ", 1)
        pairs.append((checksum, rel_path))
    return pairs


def test_write_release_evidence_checksums_writes_present_artifacts(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / "release-artifacts"
    artifacts_dir.mkdir()

    files = {
        "staged-readiness-report.json": "json-body",
        "release-evidence-manifest.md": "manifest",
        "release-evidence-reviewer-handoff.md": "handoff",
    }
    for name, content in files.items():
        (artifacts_dir / name).write_text(content, encoding="utf-8")

    output_file = artifacts_dir / "release-evidence-checksums.sha256"
    result = _run_script(
        tmp_path,
        "--artifacts-dir",
        "release-artifacts",
        "--output",
        "release-artifacts/release-evidence-checksums.sha256",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert output_file.exists()

    rows = _parse_output_lines(output_file)
    expected_names = [
        name for name in EXPECTED_ORDER if (artifacts_dir / name).exists()
    ]
    assert [Path(path).name for _, path in rows] == expected_names

    for checksum, rel_path in rows:
        path = tmp_path / rel_path
        expected_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        assert checksum == expected_checksum

    assert all(Path(path).name != output_file.name for _, path in rows)


def test_write_release_evidence_checksums_skips_missing_artifacts(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / "release-artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "staged-readiness-report.txt").write_text("txt", encoding="utf-8")

    output_file = artifacts_dir / "release-evidence-checksums.sha256"
    result = _run_script(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    rows = _parse_output_lines(output_file)
    assert len(rows) == 1
    assert rows[0][1] == "release-artifacts/staged-readiness-report.txt"


def test_write_release_evidence_checksums_is_deterministic(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "release-artifacts"
    artifacts_dir.mkdir()
    for name in [
        "release-evidence-manifest.md",
        "staged-readiness-report.json",
        "compose-validation-report.json",
    ]:
        (artifacts_dir / name).write_text(name, encoding="utf-8")

    output_file = artifacts_dir / "release-evidence-checksums.sha256"
    first = _run_script(tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    first_contents = output_file.read_text(encoding="utf-8")

    second = _run_script(tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    second_contents = output_file.read_text(encoding="utf-8")

    assert first_contents == second_contents


def test_write_release_evidence_checksums_cli_defaults(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "release-artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "release-evidence-manifest.md").write_text(
        "manifest", encoding="utf-8"
    )

    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (artifacts_dir / "release-evidence-checksums.sha256").exists()
