# veritas_os/tests/test_experiments.py
from __future__ import annotations

from typing import Any, Dict, List

import pytest

# experiment.py / experiments.py のどちらでも動くようにしておく
try:
    from veritas_os.core import experiments as exp_module  # type: ignore
except ImportError:  # pragma: no cover
    from veritas_os.core import experiment as exp_module  # type: ignore


Experiment = exp_module.Experiment
propose_experiments_for_today = exp_module.propose_experiments_for_today


def _find_by_prefix(exps: List[Experiment], prefix: str) -> Experiment:
    for e in exps:
        if e.id.startswith(prefix):
            return e
    raise AssertionError(f"no experiment with prefix {prefix!r} found")


def test_experiment_to_dict_roundtrip() -> None:
    """Experiment.to_dict が dataclass の中身を素直に dict 
化しているか。"""
    exp = Experiment(
        id="test_2025-01-01",
        title="テスト実験",
        hypothesis="テスト用に to_dict が正しく動く",
        steps=["step1", "step2"],
        expected_gain="検証しやすくなる",
        risk=0.3,
        tags=["test", "unit"],
    )

    d: Dict[str, Any] = exp.to_dict()

    assert d["id"] == "test_2025-01-01"
    assert d["title"] == "テスト実験"
    assert d["hypothesis"].startswith("テスト用に")
    assert d["steps"] == ["step1", "step2"]
    assert d["expected_gain"] == "検証しやすくなる"
    assert pytest.approx(d["risk"]) == 0.3
    assert d["tags"] == ["test", "unit"]


def test_propose_experiments_low_progress_world_state_none() -> None:
    """
    world_state=None のとき:
    - progress はデフォルト 0.0 と解釈されて S1〜S2 ブランチに入る
    - world_progress_ 系の実験が含まれている
    """
    exps = propose_experiments_for_today(user_id="user-1", 
world_state=None, value_ema=0.5)

    # 共通の診断系 2 件 + world_progress 系 1 件 = 3 件想定
    assert len(exps) == 3
    assert all(isinstance(e, Experiment) for e in exps)

    # world_progress_ で始まる id の実験が 1 つはあるはず
    _find_by_prefix(exps, "world_progress_")


def test_propose_experiments_mid_progress_uses_veritas_agi() -> None:
    """
    world_state['veritas_agi'] に progress がある場合:
    - fuji_risk_tune_ の実験が選ばれるブランチに入る
    """
    world_state = {
        "veritas_agi": {
            "progress": 0.2,        # 0.15 <= progress < 0.4 のレンジ
            "decision_count": 10,   # 使われないが行は通る
        }
    }

    exps = propose_experiments_for_today(
        user_id="user-2",
        world_state=world_state,
        value_ema=0.5,
    )

    # fuji_risk_tune_ プレフィックスの実験が含まれている
    _find_by_prefix(exps, "fuji_risk_tune_")


def test_propose_experiments_high_progress_and_risk_adjustment() -> None:
    """
    progress が高め & value_ema > 0.7 のとき:
    - usecase_loop_ 系の実験が選ばれる
    - risk < 0.15 な実験だけ risk が +0.05 され、最大 0.2 にクリップされる
    """
    world_state = {
        "veritas": {
            "progress": 0.8,        # progress >= 0.4 のレンジ
            "decision_count": 20,
        }
    }

    exps = propose_experiments_for_today(
        user_id="user-3",
        world_state=world_state,
        value_ema=0.8,  # > 0.7 なのでリスク調整ループが走る
    )

    # ブランチ確認: usecase_loop_ が含まれている
    usecase = _find_by_prefix(exps, "usecase_loop_")

    # 共通2件
    latency = _find_by_prefix(exps, "latency_check_")
    memory = _find_by_prefix(exps, "memory_hit_")

    # 初期値:
    #   latency.risk = 0.05 → 0.10 に上がる
    #   memory.risk  = 0.05 → 0.10 に上がる
    #   usecase.risk = 0.15 → そのまま（<0.15 のときだけ調整）
    assert pytest.approx(latency.risk) == 0.10
    assert pytest.approx(memory.risk) == 0.10
    assert pytest.approx(usecase.risk) == 0.15


def test_propose_experiments_value_ema_not_high_keeps_risk() -> None:
    """
    value_ema <= 0.7 の場合は risk 調整が行われないことの確認。
    """
    world_state = {
        "veritas": {
            "progress": 0.5,  # usecase_loop_ ブランチ
        }
    }

    exps = propose_experiments_for_today(
        user_id="user-4",
        world_state=world_state,
        value_ema=0.6,  # <= 0.7 → リスク調整なし
    )

    latency = _find_by_prefix(exps, "latency_check_")
    memory = _find_by_prefix(exps, "memory_hit_")
    usecase = _find_by_prefix(exps, "usecase_loop_")

    assert pytest.approx(latency.risk) == 0.05
    assert pytest.approx(memory.risk) == 0.05
    assert pytest.approx(usecase.risk) == 0.15

