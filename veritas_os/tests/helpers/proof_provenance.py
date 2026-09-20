"""Checkout identity checks shared by the two controlled E2E proofs.

This is CI/test provenance, not execution authority or a signed attestation.
``source_sha`` retains its existing PR-head meaning; ``tested_sha`` identifies
the actual checkout, which can be GitHub's synthetic PR merge commit.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]


def capture_proof_provenance(
    *,
    source_sha: str,
    base_sha: str,
    expected_tested_sha: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    """Require explicit CI identities and bind them to the checked-out commit.

    Fail before the controlled proof starts if Git is unavailable, an identity
    is missing/malformed, or the checkout differs from the CI event's SHA.
    PR head/base are metadata and need not equal the tested merge commit.
    """
    for name, value in (
        ("source_sha", source_sha),
        ("base_sha", base_sha),
        ("expected_tested_sha", expected_tested_sha),
    ):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError(f"invalid proof provenance: {name}")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise ValueError("proof checkout identity unavailable") from None
    tested_sha = result.stdout.strip()
    if tested_sha != expected_tested_sha:
        raise ValueError("proof checkout identity mismatch")
    return {
        "source_sha": source_sha,
        "base_sha": base_sha,
        "tested_sha": tested_sha,
    }


def verify_proof_provenance(
    report: Mapping[str, object],
    evidence: Mapping[str, object],
    *,
    source_sha: str,
    base_sha: str,
    expected_tested_sha: str,
    repo_root: Path = REPO_ROOT,
) -> None:
    """Recheck both artifacts against current checkout and CI event metadata.

    Agreement between two artifacts alone is insufficient: equally wrong or
    missing identities must not pass the post-proof upload gate.
    """
    expected = capture_proof_provenance(
        source_sha=source_sha,
        base_sha=base_sha,
        expected_tested_sha=expected_tested_sha,
        repo_root=repo_root,
    )
    for label, artifact in (("report", report), ("evidence", evidence)):
        for name, value in expected.items():
            if artifact.get(name) != value:
                raise ValueError(f"proof provenance mismatch: {label}.{name}")
