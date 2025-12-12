import pytest

from veritas_os.core import strategy


# ----------------------------
# ユーティリティ (_clip01)
# ----------------------------

def test_clip01_basic_and_invalid():
    # 通常ケース
    assert strategy._clip01(0.5) == 0.5
    # 下限クリップ
    assert strategy._clip01(-1.0) == 0.0
    # 上限クリップ
    assert strategy._clip01(2.0) == 1.0
    # キャストできない値 → default にフォールバック
    v = strategy._clip01("not-a-number", default=0.3)
    assert pytest.approx(v) == 0.3


# ----------------------------
# generate_options
# ----------------------------

def test_generate_options_default_uses_default_options():
    opts = strategy.generate_options(state=None, ctx=None, base=None)

    assert len(opts) == len(strategy.DEFAULT_OPTIONS)
    assert {o["id"] for o in opts} == {o["id"] for o in 
strategy.DEFAULT_OPTIONS}

    # deepcopy されていることを確認（元 DEFAULT_OPTIONS を汚さない）
    original_title = strategy.DEFAULT_OPTIONS[0]["title"]
    opts[0]["title"] = "modified"
    assert strategy.DEFAULT_OPTIONS[0]["title"] == original_title


class DummyBase:
    """model_dump を持つオブジェクト用のテストダミー。"""

    def __init__(self):
        self._data = {"id": "X", "title": "Custom", "base_score": 0.9}

    def model_dump(self):
        return dict(self._data)


def test_generate_options_with_base_and_model_dump():
    base = [DummyBase()]
    opts = strategy.generate_options(state=None, ctx=None, base=base)

    assert len(opts) == 1
    assert opts[0]["id"] == "X"
    assert opts[0]["title"] == "Custom"
    assert opts[0]["base_score"] == 0.9


# ----------------------------
# _ensure_values
# ----------------------------

class DummyValueResult:
    def __init__(self, total: float):
        self.total = total
        self.scores = {"dummy": total}
        self.top_factors = ["dummy"]
        self.rationale = "dummy-rationale"


def test_ensure_values_uses_value_core_when_missing(monkeypatch):
    """ctx に values が無い場合は value_core.evaluate を使う。"""

    def fake_evaluate(query: str, ctx: dict):
        assert "test-query" in query
        return DummyValueResult(0.8)

    monkeypatch.setattr(strategy.value_core, "evaluate", fake_evaluate)

    ctx: dict = {"query": "test-query"}
    values = strategy._ensure_values(ctx)

    assert pytest.approx(values["total"]) == 0.8
    # ctx["values"] にも保存されている
    assert "values" in ctx
    assert pytest.approx(ctx["values"]["total"]) == 0.8


def test_ensure_values_respects_existing_values(monkeypatch):
    """すでに ctx['values']['total'] があれば evaluate を呼ばない。"""

    def raising_evaluate(query: str, ctx: dict):
        raise AssertionError("evaluate should not be called")

    monkeypatch.setattr(strategy.value_core, "evaluate", raising_evaluate)

    ctx = {"values": {"total": 0.9}}
    values = strategy._ensure_values(ctx)

    assert values["total"] == 0.9


def test_ensure_values_fallback_on_error(monkeypatch):
    """evaluate が例外を投げた場合は total=0.5 にフォールバック。"""

    def bad_evaluate(query: str, ctx: dict):
        raise RuntimeError("boom")

    monkeypatch.setattr(strategy.value_core, "evaluate", bad_evaluate)

    values = strategy._ensure_values({})
    assert pytest.approx(values["total"]) == 0.5


# ----------------------------
# score_options
# ----------------------------

def test_score_options_high_utility_high_risk(monkeypatch):
    """高ユーティリティ＋高リスクのときの rationale 分岐を確認。"""

    def fake_evaluate(query: str, ctx: dict):
        return DummyValueResult(1.0)

    def fake_simulate(option: dict, state: dict):
        # utility / confidence ともに高いケース
        return {"utility": 1.0, "confidence": 1.0}

    monkeypatch.setattr(strategy.value_core, "evaluate", fake_evaluate)
    monkeypatch.setattr(strategy.wm, "simulate", fake_simulate, 
raising=False)

    ctx = {
        "fuji": {"risk": 0.9},
        "world_state": {},
        "query": "high-risk-high-return",
    }
    options = [{"id": "X", "base_score": 1.0}]

    scores = strategy.score_options(options, ctx)
    assert len(scores) == 1
    s = scores[0]
    assert s.option_id == "X"
    assert 0.0 <= s.fusion_score <= 1.0

    r = s.rationale
    assert "かなり有望なプランです" in r
    assert "FUJIリスクが高めなので慎重な検討が必要です" in r
    assert "WorldModel 上は進捗への寄与が大きそうです" in r


def test_score_options_low_risk_low_fusion(monkeypatch):
    """低リスク＋fusion が低めのときの rationale 分岐を確認。"""

    def fake_evaluate(query: str, ctx: dict):
        return DummyValueResult(0.5)

    def fake_simulate(option: dict, state: dict):
        # utility / confidence やや低め
        return {"utility": 0.4, "confidence": 0.4}

    monkeypatch.setattr(strategy.value_core, "evaluate", fake_evaluate)
    monkeypatch.setattr(strategy.wm, "simulate", fake_simulate, 
raising=False)

    ctx = {
        "fuji": {"risk": 0.1},
        "world_state": {},
        "query": "safe-but-weak",
    }
    options = [{"id": "X", "base_score": 0.5}]

    scores = strategy.score_options(options, ctx)
    s = scores[0]

    assert "優先度はやや低め" in s.rationale
    assert "FUJIリスクが比較的低く、安全寄りです" in s.rationale


def test_score_options_worldmodel_exception_fallback(monkeypatch):
    """WorldModel.simulate が失敗した場合の 0.5 フォールバックを確認。"""

    def fake_evaluate(query: str, ctx: dict):
        return DummyValueResult(0.8)

    def bad_simulate(option: dict, state: dict):
        raise RuntimeError("no world model")

    monkeypatch.setattr(strategy.value_core, "evaluate", fake_evaluate)
    monkeypatch.setattr(strategy.wm, "simulate", bad_simulate, 
raising=False)

    ctx = {"query": "no-world"}
    options = [{"id": "X", "base_score": 0.7}]

    scores = strategy.score_options(options, ctx)
    s = scores[0]

    assert pytest.approx(s.world_utility) == 0.5
    assert pytest.approx(s.world_confidence) == 0.5


# ----------------------------
# rank
# ----------------------------

def test_rank_picks_best_option_based_on_fusion(monkeypatch):
    """正常系：B がベストとして選ばれ、_veritas_scores が埋まる。"""

    options = strategy.generate_options(state=None, ctx=None, base=None)

    def fake_evaluate(query: str, ctx: dict):
        # total は全オプション同じにして base_score の差が効くようにする
        return DummyValueResult(0.5)

    def fake_simulate(option: dict, state: dict):
        # 全オプション同じ utility/confidence
        return {"utility": 0.5, "confidence": 0.5}

    monkeypatch.setattr(strategy.value_core, "evaluate", fake_evaluate)
    monkeypatch.setattr(strategy.wm, "simulate", fake_simulate, 
raising=False)

    ctx = {
        "values": {"total": 0.5},   # _ensure_values が evaluate を呼ばないように
        "fuji": {"risk": 0.0},
        "world_state": {},
    }

    best = strategy.rank(options, ctx)

    assert best["id"] == "B"  # base_score が一番高い
    assert "_veritas_scores" in best
    vs = best["_veritas_scores"]
    assert vs["option_id"] == "B"
    assert 0.0 <= vs["fusion_score"] <= 1.0


def test_rank_fallback_on_score_error(monkeypatch):
    """score_options が例外を投げた場合の B 優先フォールバックを確認。"""

    options = strategy.generate_options(state=None, ctx=None, base=None)

    def bad_score_options(opts, ctx):
        raise RuntimeError("boom")

    monkeypatch.setattr(strategy, "score_options", bad_score_options)

    best = strategy.rank(options, ctx=None)

    # フォールバックスコアのロジックで B が選ばれる
    assert best["id"] == "B"
    # フォールバック時は _veritas_scores は付かない
    assert "_veritas_scores" not in best

