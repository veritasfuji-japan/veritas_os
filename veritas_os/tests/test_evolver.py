# veritas_os/tests/test_evolver.py
from __future__ import annotations

import json
from pathlib import Path

import veritas_os.api.evolver as evolver
from veritas_os.api.schemas import PersonaState


# ------------------------------
# _extract_keywords
# ------------------------------

def test_extract_keywords_basic_properties():
    text = "VERITAS OS はプロトAGI用の Decision OS です。VERITAS テスト"
    kws = evolver._extract_keywords(text, k=5)

    # 最大 k 個・ユニークであること
    assert len(kws) <= 5
    assert len(kws) == len(set(kws))

    # 長さ降順にソートされていること
    lengths = [len(w) for w in kws]
    assert lengths == sorted(lengths, reverse=True)


# ------------------------------
# load_persona / save_persona
# ------------------------------

def test_load_persona_returns_empty_when_file_missing(tmp_path, 
monkeypatch):
    """persona.json が存在しない場合は {} を返す。"""
    persona_path = tmp_path / "persona.json"
    monkeypatch.setattr(evolver, "PERSONA_JSON", persona_path, raising=False)

    data = evolver.load_persona()
    assert data == {}


def test_load_persona_invalid_json_returns_empty(tmp_path, monkeypatch):
    """壊れた JSON の場合も安全に {} を返す。"""
    persona_path = tmp_path / "persona.json"
    persona_path.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(evolver, "PERSONA_JSON", persona_path, raising=False)

    data = evolver.load_persona()
    assert data == {}


def test_save_persona_writes_valid_json(tmp_path, monkeypatch):
    """save_persona で PersonaState が JSON として保存される。"""
    persona_path = tmp_path / "persona.json"
    monkeypatch.setattr(evolver, "PERSONA_JSON", persona_path, raising=False)

    p = PersonaState(
        name="VERITAS",
        style="base-style",
        tone="calm",
        principles=["safety", "audit"],
        last_updated="2000-01-01T00:00:00Z",
    )

    evolver.save_persona(p)

    assert persona_path.exists()

    data = json.loads(persona_path.read_text(encoding="utf-8"))
    assert data["name"] == "VERITAS"
    assert data["style"] == "base-style"
    assert data["tone"] == "calm"
    assert data["principles"] == ["safety", "audit"]
    # 上書きされた last_updated が入っていること
    assert "last_updated" in data
    assert data["last_updated"].endswith("Z")


# ------------------------------
# apply_persona
# ------------------------------

def test_apply_persona_attaches_meta_block():
    persona = PersonaState(
        name="VERITAS",
        style="nerdy",
        tone="friendly",
        principles=["safety"],
        last_updated="2024-01-01T00:00:00Z",
    )
    chosen = {"title": "some decision"}

    enriched = evolver.apply_persona(chosen, persona)

    # 元のフィールドが残っている
    assert enriched["title"] == "some decision"

    meta = enriched["_persona"]
    assert meta["name"] == "VERITAS"
    assert meta["style"] == "nerdy"
    assert meta["tone"] == "friendly"
    assert meta["principles"] == ["safety"]


# ------------------------------
# evolve_persona
# ------------------------------

def test_evolve_persona_no_change_without_keywords():
    persona = PersonaState(
        name="VERITAS",
        style="base-style",
        tone="calm",
        principles=[],
        last_updated="2024-01-01T00:00:00Z",
    )
    evo = {"insights": {"keywords": ["その他", "雑談"]}}

    new_persona = evolver.evolve_persona(persona, evo)

    # キーワードが無いので style は変わらない
    assert new_persona.style == "base-style"


def test_evolve_persona_adds_evidence_first_on_research_keywords():
    persona = PersonaState(
        name="VERITAS",
        style="base-style",
        tone="calm",
        principles=[],
        last_updated="2024-01-01T00:00:00Z",
    )
    evo = {"insights": {"keywords": ["研究", "実証"]}}

    new_persona = evolver.evolve_persona(persona, evo)

    # 進化後の style に evidence-first が付与される
    assert "evidence-first" in new_persona.style
    # 元の persona は副作用で書き換わっていない
    assert persona.style == "base-style"


# ------------------------------
# generate_suggestions
# ------------------------------

def test_generate_suggestions_includes_actions_and_next_prompts():
    query = "VERITAS OS の評価と今後のAGI開発方針について"
    chosen = {
        "text": "これは検証のための説明文です。",
        "uncertainty": 0.7,  # 0.6 より大きい → 一次情報アクションが入る
    }
    alts = [{"title": "alt-plan"}]

    res = evolver.generate_suggestions(query, chosen, alts)

    # 返却構造
    assert "insights" in res
    assert "actions" in res
    assert "next_prompts" in res
    assert "notes" in res

    # キーワードは最大6個
    kws = res["insights"]["keywords"]
    assert len(kws) <= 6

    actions = res["actions"]
    next_prompts = res["next_prompts"]

    # 不確実性が高いときの一次情報アクション
    assert any("一次情報" in a for a in actions)
    assert any("一次情報" in p for p in next_prompts)

    # 代替案統合アクション
    assert any("代替案の強みだけを統合して最適案を作る" in a for a in actions)
    assert any("代替案の強みだけを統合した最適案を出して" in p for p in next_prompts)

    # 30分検証ステップ
    assert any("30分で検証できる最小ステップ" in a for a in actions)


def test_generate_suggestions_handles_non_numeric_uncertainty():
    """uncertainty が数値変換できなくても落ちないこと。"""
    query = "テストクエリ"
    chosen = {
        "text": "本文",
        "uncertainty": "not-a-number",  # float() で例外 → except branch
    }

    res = evolver.generate_suggestions(query, chosen, alts=[])

    assert "actions" in res
    assert "next_prompts" in res
    # 最低限、30分ステップの提案は含まれている
    assert any("30分で検証できる最小ステップ" in a for a in res["actions"])

