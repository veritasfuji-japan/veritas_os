"""Structural regression tests for the optional AuthorityEvidence crypto backend."""

from pathlib import Path


def test_core_authority_module_does_not_import_cryptography() -> None:
    """Keep core governance imports independent from the signing extra."""
    source = Path("veritas_os/governance/authority_evidence.py").read_text(
        encoding="utf-8"
    )
    assert "from cryptography" not in source
    assert "import cryptography" not in source


def test_optional_backend_owns_cryptography_import() -> None:
    """Make the signing capability boundary explicit and reviewable."""
    source = Path(
        "veritas_os/governance/authority_evidence_signing.py"
    ).read_text(encoding="utf-8")
    assert "from cryptography" in source
