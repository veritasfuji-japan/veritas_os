# tests/test_adapt.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from veritas_os.core import adapt


# ===============================
# clean_bias_weights
# ===============================

def test_clean_bias_weights_none_and_empty():
    assert adapt.clean_bias_weights(None) == {}
    assert adapt.clean_bias_weights({}) == {}


def test_clean_bias_weights_normalizes_and_clips():
    bias = {
        "a": 0.2,
        "b": 0.4,
        "c": "0.1",   # 文字列でも float 変換される
    }
    cleaned = adapt.clean_bias_weights(bias)

    # 最大値 0.4 で正規化 → 0.2/0.4 = 0.5, 0.4/0.4 = 1.0, 0.1/0.4 = 0.25
    assert cleaned["a"] == 0.5
    assert cleaned["b"] == 1.0
    assert cleaned["c"] == 0.25

    # 0〜1 の範囲内
    for v in cleaned.values():
        assert 0.0 <= v <= 1.0


def test_clean_bias_weights_clips_and_zero_small_values():
    bias = {
        "neg": -1.0,     # 0 にクリップ
        "big": 2.0,      # 1 にクリップ
        "tiny": 1e-6,    # zero_eps(1e-4) 未満 → 0 扱い
    }
    cleaned = adapt.clean_bias_weights(bias)

    assert cleaned["big"] == 1.0
    assert cleaned["neg"] == 0.0
    assert cleaned["tiny"] == 0.0


def test_clean_bias_weights_all_zero_branch():
    # すべて 0 → mx <= 0.0 の分岐
    bias = {"a": 0.0, "b": 0.0}
    cleaned = adapt.clean_bias_weights(bias)
    assert cleaned == {"a": 0.0, "b": 0.0}


def test_clean_bias_weights_invalid_value_becomes_zero():
    class Dummy:
        pass

    bias = {"x": Dummy()}  # float() できない → 0.0
    cleaned = adapt.clean_bias_weights(bias)
    assert cleaned["x"] == 0.0


# ===============================
# load_persona / save_persona
# ===============================

def test_load_persona_missing_file_returns_default(tmp_path: Path):
    path = tmp_path / "persona_missing.json"
    persona = adapt.load_persona(str(path))

    assert isinstance(persona, dict)
    assert persona["name"] == "VERITAS"
    assert "bias_weights" in persona
    assert isinstance(persona["bias_weights"], dict)
    assert persona["bias_weights"] == {}


def test_load_persona_invalid_type_falls_back_to_default(tmp_path: Path):
    path = tmp_path / "persona_invalid.json"
    path.write_text("[]", encoding="utf-8")  # dict ではない

    persona = adapt.load_persona(str(path))
    assert persona["name"] == "VERITAS"
    assert persona["bias_weights"] == {}


def test_load_persona_cleans_bias_weights(tmp_path: Path):
    path = tmp_path / "persona.json"
    raw = {
        "name": "Custom",
        "style": "test",
        "bias_weights": {"A": 2.0, "B": 0.0},
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    persona = adapt.load_persona(str(path))
    assert persona["name"] == "Custom"
    # 2.0 → 1.0 に正規化される想定
    assert persona["bias_weights"]["A"] == 1.0
    assert persona["bias_weights"]["B"] == 0.0


def test_save_persona_creates_dir_and_cleans(tmp_path: Path):
    persona_path = tmp_path / "subdir" / "persona.json"
    persona = {
        "name": "X",
        "style": "s",
        "bias_weights": {
            "A": 2.0,       # → 1.0
            "B": 0.00001,   # zero_eps 未満 → 0.0
        },
    }

    adapt.save_persona(persona, str(persona_path))
    assert persona_path.exists()

    saved = json.loads(persona_path.read_text(encoding="utf-8"))
    assert saved["name"] == "X"
    assert saved["bias_weights"]["A"] == 1.0
    assert saved["bias_weights"]["B"] == 0.0


# ===============================
# read_recent_decisions
# ===============================

def test_read_recent_decisions_missing_file(tmp_path: Path):
    path = tmp_path / "trust_missing.jsonl"
    result = adapt.read_recent_decisions(str(path), window=10)
    assert result == []


def test_read_recent_decisions_filters_and_limits(tmp_path: Path):
    path = tmp_path / "trust_log.jsonl"
    lines = [
        json.dumps({"chosen": {"id": "1", "title": "A"}}),
        "not a json",
        json.dumps({"no_chosen": True}),
        json.dumps({"chosen": {"id": "2", "title": "B"}}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = adapt.read_recent_decisions(str(path), window=2)
    titles = [item["title"] for item in result]

    # valid line 1(A) + 4(B) の2件
    assert titles == ["A", "B"]


# ===============================
# compute_bias_from_history
# ===============================

def test_compute_bias_from_history_empty():
    assert adapt.compute_bias_from_history([]) == {}


def test_compute_bias_from_history_mixed_titles_and_ids():
    decisions: List[Dict[str, Any]] = [
        {"id": "1", "title": "Foo"},
        {"id": "2", "title": "Foo"},
        {"id": "3", "title": ""},   # タイトルなし → id で集計
        {"id": "4"},
    ]

    bias = adapt.compute_bias_from_history(decisions)

    # "foo" 2回, "@id:3" 1回, "@id:4" 1回 → 合計4
    assert set(bias.keys()) == {"foo", "@id:3", "@id:4"}

    assert pytest.approx(bias["foo"], rel=1e-6) == 2.0 / 4.0
    assert pytest.approx(bias["@id:3"], rel=1e-6) == 1.0 / 4.0
    assert pytest.approx(bias["@id:4"], rel=1e-6) == 1.0 / 4.0

    # 念のため合計 1.0 もチェック
    assert pytest.approx(sum(bias.values()), rel=1e-6) == 1.0



# ===============================
# merge_bias_to_persona
# ===============================

def test_merge_bias_to_persona_unions_keys_and_normalizes():
    persona = {
        "name": "P",
        "bias_weights": {"foo": 0.5},
    }
    new_bias = {"bar": 1.0}

    merged = adapt.merge_bias_to_persona(persona, new_bias, alpha=0.5)
    bw = merged["bias_weights"]

    # キーがユニオンされていること
    assert set(bw.keys()) == {"foo", "bar"}

    # 0〜1 の範囲内で正規化されていること
    for v in bw.values():
        assert 0.0 <= v <= 1.0

    # このケースだと foo と bar は同じ重み（対称）になるはず
    assert pytest.approx(bw["foo"], rel=1e-6) == bw["bar"]


# ===============================
# fuzzy_bias_lookup
# ===============================

def test_fuzzy_bias_lookup_matches_keywords():
    bias_weights = {
        "refactor core": 0.8,
        "other thing": 0.2,
        "@id:xyz": 1.0,  # id は lookup からは除外される
    }
    title = "Big CORE refactor plan"

    score = adapt.fuzzy_bias_lookup(bias_weights, title)
    assert score == 0.8


def test_fuzzy_bias_lookup_uses_max_weight_when_multiple_match():
    bias_weights = {
        "risk reduction": 0.3,
        "reduction plan": 0.9,
    }
    title = "New risk reduction plan for Q4"

    score = adapt.fuzzy_bias_lookup(bias_weights, title)
    # 両方マッチするが、最大重み 0.9 が返る想定
    assert score == 0.9


def test_fuzzy_bias_lookup_ignores_id_keys_and_handles_no_match():
    bias_weights = {
        "@id:123": 1.0,
        "something": 0.5,
    }
    # どれもマッチしない
    score = adapt.fuzzy_bias_lookup(bias_weights, "unrelated title")
    assert score == 0.0

    # bias_weights 空 or title 空でも 0.0
    assert adapt.fuzzy_bias_lookup({}, "test") == 0.0
    assert adapt.fuzzy_bias_lookup({"x": 0.5}, "") == 0.0


# ===============================
# update_persona_bias_from_history
# ===============================

def test_update_persona_bias_from_history_no_history(monkeypatch, tmp_path: Path):
    # trust_log が存在しない or bias が空のときは persona を変更しない＆保存もしない
    trust_path = tmp_path / "trust_empty.jsonl"

    def fake_load_persona(path: str = "") -> Dict[str, Any]:
        return {"name": "P", "bias_weights": {"existing": 1.0}}

    saved: List[Dict[str, Any]] = []

    def fake_save_persona(persona: Dict[str, Any], path: str = "") -> None:
        saved.append(persona)

    monkeypatch.setattr(adapt, "load_persona", fake_load_persona)
    monkeypatch.setattr(adapt, "save_persona", fake_save_persona)
    monkeypatch.setattr(adapt, "TRUST_JSONL", str(trust_path))

    updated = adapt.update_persona_bias_from_history(window=10)
    assert updated["bias_weights"] == {"existing": 1.0}
    # save_persona は呼ばれない想定
    assert saved == []


def test_update_persona_bias_from_history_merges_and_persists(monkeypatch, tmp_path: Path):
    trust_path = tmp_path / "trust_log.jsonl"
    persona_path = tmp_path / "persona.json"

    # refactor core が 2回, add feature が 1回
    lines = [
        json.dumps({"chosen": {"id": "a1", "title": "Refactor Core"}}),
        json.dumps({"chosen": {"id": "a2", "title": "Refactor Core"}}),
        json.dumps({"chosen": {"id": "b1", "title": "Add Feature"}}),
    ]
    trust_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def fake_load_persona(path: str = str(persona_path)) -> Dict[str, Any]:
        if persona_path.exists():
            return json.loads(persona_path.read_text(encoding="utf-8"))
        return {"name": "P", "bias_weights": {}}

    def fake_save_persona(persona: Dict[str, Any], path: str = str(persona_path)) -> None:
        persona_path.parent.mkdir(parents=True, exist_ok=True)
        persona_path.write_text(json.dumps(persona, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(adapt, "load_persona", fake_load_persona)
    monkeypatch.setattr(adapt, "save_persona", fake_save_persona)
    monkeypatch.setattr(adapt, "TRUST_JSONL", str(trust_path))

    updated = adapt.update_persona_bias_from_history(window=10)

    # ファイルにも保存されていることを確認
    persisted = json.loads(persona_path.read_text(encoding="utf-8"))
    assert persisted["bias_weights"] == updated["bias_weights"]

    bw = updated["bias_weights"]
    # タイトルは lower() される
    assert set(bw.keys()) == {"refactor core", "add feature"}
    # 2:1 の頻度 → EMA → 正規化後も比率は 2:1 になる（1.0 と 0.5）
    assert bw["refactor core"] == 1.0
    assert bw["add feature"] == 0.5

