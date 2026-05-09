"""Documentation coverage checks for external security remediation summary."""

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_external_security_remediation_docs_exist() -> None:
    assert Path("docs/en/security/external-security-remediation-summary.md").exists()
    assert Path("docs/ja/security/external-security-remediation-summary.md").exists()


def test_en_doc_contains_findings() -> None:
    content = _read("docs/en/security/external-security-remediation-summary.md")
    for finding in ["#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8"]:
        assert finding in content


def test_en_doc_contains_pr_refs() -> None:
    content = _read("docs/en/security/external-security-remediation-summary.md")
    for pr_ref in ["#1660", "#1661", "#1664", "#1666", "#1667", "#1668", "#1669"]:
        assert pr_ref in content


def test_en_doc_contains_non_claim_boundaries() -> None:
    content = _read("docs/en/security/external-security-remediation-summary.md")
    required = [
        "not a third-party certification",
        "does not claim production SLA",
        "does not claim",
        "formal penetration test",
        "legal certification",
    ]
    for phrase in required:
        assert phrase in content


def test_en_doc_contains_verification_commands() -> None:
    content = _read("docs/en/security/external-security-remediation-summary.md")
    commands = [
        "pytest -q veritas_os/tests/test_docker_compose_security.py",
        "pytest -q veritas_os/tests/test_signing_key_file_hardening.py",
        "pytest -q veritas_os/tests/test_kms_verify_error_handling.py",
        "pytest -q veritas_os/tests/test_wat_verifier_post_checks.py",
        "python scripts/quality/check_deployment_env_defaults.py",
    ]
    for command in commands:
        assert command in content


def test_ja_doc_contains_required_phrases() -> None:
    content = _read("docs/ja/security/external-security-remediation-summary.md")
    required = ["第三者認証", "本番SLA", "脆弱性ゼロ", "英語版が正本", "#1660", "#1669"]
    for phrase in required:
        assert phrase in content


def test_index_links_exist() -> None:
    assert "external-security-remediation-summary.md" in _read("README.md")
    assert "docs/en/security/external-security-remediation-summary.md" in _read(
        "README.md"
    )
    assert "docs/ja/security/external-security-remediation-summary.md" in _read(
        "README.md"
    )
    assert "external-security-remediation-summary.md" in _read("README_JP.md")
    assert "docs/ja/security/external-security-remediation-summary.md" in _read(
        "README_JP.md"
    )
    assert "docs/en/security/external-security-remediation-summary.md" in _read(
        "README_JP.md"
    )
    assert "英語正本" in _read("README_JP.md")
    assert "external-security-remediation-summary.md" in _read("docs/INDEX.md")
    assert "external-security-remediation-summary.md" in _read("docs/DOCUMENTATION_MAP.md")


def test_remediation_matrix_tables_do_not_start_with_double_pipe() -> None:
    for path in [
        "docs/en/security/external-security-remediation-summary.md",
        "docs/ja/security/external-security-remediation-summary.md",
    ]:
        for line in _read(path).splitlines():
            assert not line.startswith("||"), (
                f"{path} contains malformed table row: {line}"
            )
