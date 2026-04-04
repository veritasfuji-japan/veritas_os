"""Tests for dependency-profile extras defined in pyproject.toml.

Validates that:
- pyproject.toml declares the expected extras groups
- requirements.txt stays in sync with pyproject.toml
- Core dependencies remain in the top-level ``dependencies`` list
- Optional packages are only in extras, not in core
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:  # pragma: no cover
        raise ImportError(
            "Python <3.11 requires the 'tomli' package: pip install tomli"
        )

_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _ROOT / "pyproject.toml"
_REQUIREMENTS = _ROOT / "veritas_os" / "requirements.txt"

# --- Expected extras groups ---------------------------------------------------

EXPECTED_EXTRAS = {"ml", "reports", "anthropic", "system", "observability", "signing", "full"}

EXPECTED_CORE = {
    "fastapi",
    "uvicorn",
    "pydantic",
    "python-dotenv",
    "orjson",
    "pyyaml",
    "openai",
    "httpx",
    "jinja2",
    "numpy",
}

EXPECTED_OPTIONAL = {
    "scikit-learn",
    "sentence-transformers",
    "matplotlib",
    "pandas",
    "pdfplumber",
    "pdfminer.six",
    "anthropic",
    "psutil",
    "trio",
    "starlette",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp",
    "prometheus-client",
    "cryptography",
}


def _load_pyproject() -> dict:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def _parse_pkg_name(spec: str) -> str:
    """Extract package name from a PEP 508 dependency specifier."""
    # Handle self-referencing extras like "veritas-os[ml,reports,...]"
    name = spec.split("[")[0].split("==")[0].split(">=")[0].split("<=")[0]
    return name.strip().lower()


def _read_requirements_packages() -> set[str]:
    """Return set of lowercase package names from requirements.txt."""
    pkgs: set[str] = set()
    for line in _REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkgs.add(_parse_pkg_name(line))
    return pkgs


# --- Tests --------------------------------------------------------------------


class TestPyprojectExtras:
    """Validate [project.optional-dependencies] structure in pyproject.toml."""

    def test_extras_groups_exist(self) -> None:
        data = _load_pyproject()
        extras = data.get("project", {}).get("optional-dependencies", {})
        assert set(extras.keys()) == EXPECTED_EXTRAS, (
            f"Expected extras {EXPECTED_EXTRAS}, got {set(extras.keys())}"
        )

    def test_full_extra_references_all_groups(self) -> None:
        data = _load_pyproject()
        extras = data.get("project", {}).get("optional-dependencies", {})
        full_specs = extras.get("full", [])
        # full should reference all other extras via self-referencing
        other_groups = EXPECTED_EXTRAS - {"full"}
        for group in other_groups:
            assert any(group in spec for spec in full_specs), (
                f"'full' extra does not reference '{group}'"
            )

    def test_core_deps_are_in_dependencies(self) -> None:
        data = _load_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        dep_names = {_parse_pkg_name(d) for d in deps}
        for pkg in EXPECTED_CORE:
            assert pkg in dep_names, (
                f"Core package '{pkg}' missing from [project].dependencies"
            )

    def test_optional_deps_not_in_core(self) -> None:
        data = _load_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        dep_names = {_parse_pkg_name(d) for d in deps}
        for pkg in EXPECTED_OPTIONAL:
            assert pkg not in dep_names, (
                f"Optional package '{pkg}' should not be in [project].dependencies; "
                "move it to [project.optional-dependencies]"
            )

    def test_all_extras_packages_are_pinned(self) -> None:
        """Every extras entry (except self-refs) should pin a version with ==."""
        data = _load_pyproject()
        extras = data.get("project", {}).get("optional-dependencies", {})
        for group, specs in extras.items():
            for spec in specs:
                if spec.startswith("veritas-os"):
                    continue  # self-referencing extra
                if group == "observability":
                    assert ">=" in spec or "==" in spec, (
                        f"Observability extras [{group}] entry '{spec}' "
                        "must define a minimum or exact version"
                    )
                    continue
                assert "==" in spec, (
                    f"Extras [{group}] entry '{spec}' is not pinned with =="
                )


class TestRequirementsTxtSync:
    """requirements.txt must be a superset of all pyproject.toml packages."""

    def test_all_pyproject_deps_in_requirements(self) -> None:
        data = _load_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        extras = data.get("project", {}).get("optional-dependencies", {})

        pyproject_pkgs: set[str] = set()
        for spec in deps:
            pyproject_pkgs.add(_parse_pkg_name(spec))
        for group, specs in extras.items():
            for spec in specs:
                if spec.startswith("veritas-os"):
                    continue
                pyproject_pkgs.add(_parse_pkg_name(spec))

        req_pkgs = _read_requirements_packages()
        missing = pyproject_pkgs - req_pkgs
        assert not missing, (
            f"Packages in pyproject.toml but not in requirements.txt: {missing}"
        )

    def test_requirements_has_no_unknown_packages(self) -> None:
        data = _load_pyproject()
        deps = data.get("project", {}).get("dependencies", [])
        extras = data.get("project", {}).get("optional-dependencies", {})

        pyproject_pkgs: set[str] = set()
        for spec in deps:
            pyproject_pkgs.add(_parse_pkg_name(spec))
        for group, specs in extras.items():
            for spec in specs:
                if spec.startswith("veritas-os"):
                    continue
                pyproject_pkgs.add(_parse_pkg_name(spec))

        req_pkgs = _read_requirements_packages()
        extra = req_pkgs - pyproject_pkgs
        assert not extra, (
            f"Packages in requirements.txt but not in pyproject.toml: {extra}"
        )
