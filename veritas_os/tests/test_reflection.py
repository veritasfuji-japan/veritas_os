from __future__ import annotations

from typing import Any, Dict, List

from veritas_os.core import reflection


class StubTrustLog:
    """trust_log.evaluate のスタブ。"""

    def __init__(self, score: float):
        self.score = score
        self.calls: List[tuple[Any, Dict[str, Any]]] = []

    def evaluate(self, decision: Any, outcome: Dict[str, Any]) -> float:
        self.calls.append((decision, outcome))
        return self.score


class StubValueCore:
    """value_core.adjust_weights の呼び出し履歴だけ取るスタブ。"""

    calls: List[tuple[str, float]] = []

    @staticmethod
    def adjust_weights(name: str, delta: float) -> None:
        StubValueCore.calls.append((name, delta))


class DecisionWithId:
    def __init__(self, id_: str) -> None:
        self.id = id_


def test_evaluate_decision_low_score_adjusts_weights_and_logs(monkeypatch):
    """score < 0.5 のときに adjust_weights が呼ばれ、memory にも記録される。"""
    tl = StubTrustLog(0.4)
    StubValueCore.calls = []

    monkeypatch.setattr(reflection, "trust_log", tl, raising=False)
    monkeypatch.setattr(reflection, "value_core", StubValueCore, raising=False)

    memory: List[Dict[str, Any]] = []
    decision = DecisionWithId("d-1")

    score = reflection.evaluate_decision(decision, {"any": "thing"}, memory)

    assert score == 0.4
    assert tl.calls  # evaluate が1回以上呼ばれている
    assert memory == [{"decision_id": "d-1", "score": 0.4}]
    # prudence が +0.1 されている
    assert StubValueCore.calls == [("prudence", 0.1)]


def test_evaluate_decision_high_score_does_not_adjust_weights(monkeypatch):
    """score >= 0.5 のときは adjust_weights が呼ばれない。"""
    tl = StubTrustLog(0.9)
    StubValueCore.calls = []

    monkeypatch.setattr(reflection, "trust_log", tl, raising=False)
    monkeypatch.setattr(reflection, "value_core", StubValueCore, raising=False)

    memory: List[Dict[str, Any]] = []
    decision = DecisionWithId("d-2")

    score = reflection.evaluate_decision(decision, {"score": 0.1}, memory)

    assert score == 0.9
    assert memory == [{"decision_id": "d-2", "score": 0.9}]
    # スコアが高いので prudence はいじらない
    assert StubValueCore.calls == []


def test_evaluate_decision_uses_outcome_score_when_no_trust_log_evaluate(monkeypatch):
    """
    trust_log に evaluate が無い場合、
    outcome["score"] が使われる & prudence が調整される。
    """
    StubValueCore.calls = []

    # evaluate を持たないダミー trust_log
    monkeypatch.setattr(reflection, "trust_log", object(), raising=False)
    monkeypatch.setattr(reflection, "value_core", StubValueCore, raising=False)

    memory: List[Dict[str, Any]] = []
    decision = {"id": "dict-1"}

    score = reflection.evaluate_decision(decision, {"score": 0.3}, memory)

    assert score == 0.3
    assert memory == [{"decision_id": "dict-1", "score": 0.3}]
    # 0.3 < 0.5 なので prudence が強化される
    assert StubValueCore.calls == [("prudence", 0.1)]


def test_evaluate_decision_defaults_to_neutral_when_no_score(monkeypatch):
    """
    trust_log.evaluate も outcome["score"] も無い場合は 0.5 を返し、
    prudence の調整は行わない。
    """
    StubValueCore.calls = []

    monkeypatch.setattr(reflection, "trust_log", object(), raising=False)
    monkeypatch.setattr(reflection, "value_core", StubValueCore, raising=False)

    memory: List[Dict[str, Any]] = []
    decision = "plain-decision"

    score = reflection.evaluate_decision(decision, {}, memory)

    assert score == 0.5
    assert memory == [{"decision_id": "plain-decision", "score": 0.5}]
    assert StubValueCore.calls == []


def test_evaluate_decision_raises_on_none_memory(monkeypatch):
    """memory=None は明示的にエラーにしておく。"""
    import pytest

    monkeypatch.setattr(reflection, "trust_log", object(), raising=False)
    monkeypatch.setattr(reflection, "value_core", StubValueCore, raising=False)

    with pytest.raises(ValueError):
        reflection.evaluate_decision("x", {"score": 0.1}, None)  # type: ignore[arg-type]

