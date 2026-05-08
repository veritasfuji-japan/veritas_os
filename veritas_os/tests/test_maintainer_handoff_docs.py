"""Docs checks for maintainer handoff and support continuity runbook."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EN_DOC = REPO_ROOT / "docs/en/operations/maintainer-handoff.md"
JA_DOC = REPO_ROOT / "docs/ja/operations/maintainer-handoff.md"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_maintainer_handoff_docs_exist() -> None:
    assert EN_DOC.exists()
    assert JA_DOC.exists()


def test_readme_index_and_map_link_handoff_docs() -> None:
    assert "docs/en/operations/maintainer-handoff.md" in _read("README.md")
    assert "maintainer-handoff.md" in _read("docs/INDEX.md")
    assert "maintainer-handoff.md" in _read("docs/DOCUMENTATION_MAP.md")


def test_risk_boundary_phrases_exist() -> None:
    en = EN_DOC.read_text(encoding="utf-8")
    ja = JA_DOC.read_text(encoding="utf-8")
    assert "does not eliminate bus-factor risk" in en
    assert "not a substitute for a staffed support organization" in en
    assert "no formal support SLA" in en
    assert "バスファクターリスクを完全に解消するものではありません" in ja
    assert "24/7 support または正式なSLAを意味しない" in ja


def test_required_sections_exist_in_english_doc() -> None:
    text = EN_DOC.read_text(encoding="utf-8")
    required = [
        "First 60 minutes",
        "Quality gates checklist",
        "PR review checklist",
        "Incident triage checklist",
        "Current known continuity risks",
    ]
    for phrase in required:
        assert phrase in text


def test_no_overclaim_phrases() -> None:
    targets = [
        "docs/en/operations/maintainer-handoff.md",
        "docs/ja/operations/maintainer-handoff.md",
        "README.md",
    ]
    banned = [
        "bus factor solved",
        "eliminates bus-factor risk",
        "24/7 support guaranteed",
        "formal SLA included",
        "バスファクター解決済み",
        "24時間365日サポート保証",
        "正式SLA提供済み",
    ]
    for path in targets:
        text = _read(path)
        for phrase in banned:
            assert phrase not in text
