"""Docs checks for provider support matrix positioning and coverage."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EN_MATRIX = REPO_ROOT / "docs/en/operations/provider-support-matrix.md"
JA_MATRIX = REPO_ROOT / "docs/ja/operations/provider-support-matrix.md"
LLM_CLIENT = REPO_ROOT / "veritas_os/core/llm_client.py"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _provider_tiers_from_source() -> dict[str, str]:
    source = LLM_CLIENT.read_text(encoding="utf-8")
    pattern = re.compile(r"LLMProvider\.([A-Z_]+)\.value:\s*SupportTier\.([A-Z_]+)")
    return {match.group(1).lower(): match.group(2).lower() for match in pattern.finditer(source)}


def test_provider_support_matrix_docs_exist() -> None:
    assert EN_MATRIX.exists()
    assert JA_MATRIX.exists()


def test_readme_links_provider_support_matrix() -> None:
    assert "docs/en/operations/provider-support-matrix.md" in _read("README.md")


def test_index_and_map_include_provider_support_matrix() -> None:
    assert "provider-support-matrix.md" in _read("docs/INDEX.md")
    assert "provider-support-matrix.md" in _read("docs/DOCUMENTATION_MAP.md")


def test_provider_support_matrix_mentions_all_configured_providers() -> None:
    text = EN_MATRIX.read_text(encoding="utf-8").lower()
    for provider in _provider_tiers_from_source():
        assert provider in text


def test_docs_do_not_overstate_non_openai_production_support() -> None:
    provider_tiers = _provider_tiers_from_source()
    production_providers = {name for name, tier in provider_tiers.items() if tier == "production"}
    assert production_providers == {"openai"}
    assert "OpenAI | Production" in EN_MATRIX.read_text(encoding="utf-8")


def test_provider_positioning_banned_claims_absent() -> None:
    targets = [
        "docs/en/operations/provider-support-matrix.md",
        "docs/ja/operations/provider-support-matrix.md",
        "docs/en/poc/one-day-poc-reviewer-pack.md",
        "docs/ja/poc/one-day-poc-reviewer-pack.md",
    ]
    banned = [
        "provider-neutral production support",
        "on-prem supported",
        "private cloud ready",
        "all providers are production-ready",
        "OpenAI-independent production runtime",
    ]
    for path in targets:
        text = _read(path)
        for phrase in banned:
            assert phrase not in text


def test_eu_ai_act_provider_note_is_japanese_positioning() -> None:
    text = _read("docs/eu_ai_act/technical_documentation.md")
    assert "Provider選定と責任境界" in text
    assert "Provider selection and responsibility boundary" not in text
