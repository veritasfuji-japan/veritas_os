"""Keep the lightweight CI dependency profile exact and reviewable."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FULL_REQUIREMENTS = REPOSITORY_ROOT / "veritas_os" / "requirements.txt"
CI_REQUIREMENTS = REPOSITORY_ROOT / "veritas_os" / "requirements-ci.txt"
EXPECTED_CI_OMISSIONS = {
    "scikit-learn==1.5.2",
    "sentence-transformers==5.3.0",
    "transformers==5.5.0",
}


def _read_requirements(path: Path) -> set[str]:
    requirements: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            requirements.update(_read_requirements(path.parent / line[3:].strip()))
            continue
        requirements.add(line)
    return requirements


def test_ci_profile_is_full_profile_without_optional_ml() -> None:
    full = _read_requirements(FULL_REQUIREMENTS)
    ci = _read_requirements(CI_REQUIREMENTS)

    assert ci <= full
    assert full - ci == EXPECTED_CI_OMISSIONS
