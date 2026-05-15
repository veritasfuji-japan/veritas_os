"""Write SHA256 checksums for present release evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXPECTED_ARTIFACTS = [
    "release-evidence-manifest.md",
    "release-evidence-reviewer-handoff.md",
    "staged-readiness-report.json",
    "staged-readiness-report.txt",
    "compose-validation-report.json",
    "live-provider-report.json",
]


def _sha256_hex(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _display_artifacts_dir(artifacts_dir: Path) -> Path:
    """Return a portable display directory for checksum entries."""
    if artifacts_dir.is_absolute():
        return Path(artifacts_dir.name)

    normalized_parts = [part for part in artifacts_dir.parts if part not in ("", ".")]
    if not normalized_parts:
        return Path("release-artifacts")
    return Path(*normalized_parts)


def _display_path(display_artifacts_dir: Path, artifact_name: str) -> str:
    """Return a portable checksum display path for an artifact."""
    return (display_artifacts_dir / artifact_name).as_posix()


def write_release_evidence_checksums(artifacts_dir: Path, output: Path) -> int:
    """Write checksums for present expected artifacts and return count."""
    raw_artifacts_dir = artifacts_dir
    display_artifacts_dir = _display_artifacts_dir(raw_artifacts_dir)

    artifacts_dir = artifacts_dir.resolve()
    output = output.resolve()

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    count = 0

    for artifact_name in EXPECTED_ARTIFACTS:
        artifact_path = artifacts_dir / artifact_name
        if not artifact_path.exists() or artifact_path.resolve() == output.resolve():
            continue
        digest = _sha256_hex(artifact_path)
        lines.append(f"{digest}  {_display_path(display_artifacts_dir, artifact_name)}")
        count += 1

    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"Wrote {count} checksums to {output.as_posix()}")
    return count


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Write checksums for present release evidence artifacts."
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("release-artifacts"),
        help="Directory containing release artifacts (default: release-artifacts)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release-artifacts/release-evidence-checksums.sha256"),
        help=(
            "Output checksum file "
            "(default: release-artifacts/release-evidence-checksums.sha256)"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    write_release_evidence_checksums(args.artifacts_dir, args.output)


if __name__ == "__main__":
    main()
