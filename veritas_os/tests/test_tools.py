# veritas_os/tests/test_telos.py
# -*- coding: utf-8 -*-

import math

from veritas_os.api import telos


def test_telos_score_default_context_is_clamped_and_not_nan():
    """context={} でも 0〜1 に収まり、NaN にならないことだけ保証。"""
    score = telos.telos_score({})
    assert 0.0 <= score <= 1.0
    assert not math.isnan(score)


def test_telos_score_risk_high_vs_low():
    """
    FUJI リスクが高いほど telos スコアが下がることを確認。
    （他の条件は同一にして比較）
    """
    base_ctx = {
        "telos_weights": {"W_Transcendence": 0.8, "W_Struggle": 0.2},
        "time_horizon": "mid",
        "world": {"predicted_progress": 0.8},
        "value_ema": 0.8,
    }

    safe_ctx = {**base_ctx, "fuji_status": {"risk": 0.0}}
    risky_ctx = {**base_ctx, "fuji_status": {"risk": 0.9}}

    safe_score = telos.telos_score(safe_ctx)
    risky_score = telos.telos_score(risky_ctx)

    assert 0.0 <= safe_score <= 1.0
    assert 0.0 <= risky_score <= 1.0
    assert safe_score > risky_score


def test_telos_score_horizon_short_mid_long():
    """
    time_horizon によってスコアが変化すること。
    デフォルト設定では short < mid < long の想定。
    """
    base_ctx = {
        "fuji_status": {"risk": 0.0},
        "world": {"predicted_progress": 0.5},
        "value_ema": 0.5,
        "telos_weights": {"W_Transcendence": 0.6, "W_Struggle": 0.4},
    }

    short_ctx = {**base_ctx, "time_horizon": "short"}
    mid_ctx = {**base_ctx, "time_horizon": "mid"}
    long_ctx = {**base_ctx, "time_horizon": "long"}

    s_short = telos.telos_score(short_ctx)
    s_mid = telos.telos_score(mid_ctx)
    s_long = telos.telos_score(long_ctx)

    assert 0.0 <= s_short <= 1.0
    assert 0.0 <= s_mid <= 1.0
    assert 0.0 <= s_long <= 1.0

        # デフォルトの TelosConfig を前提にした期待関係
    # horizon_factor としては short < mid < long だが、
    # clamp(0..1) のため mid / long がどちらも 1.0 に張り付くケースを許容する。
    assert s_short < s_mid
    assert s_mid <= s_long



def test_telos_unknown_horizon_falls_back_to_mid():
    """
    不明な time_horizon の場合、mid とほぼ同じスコアになること。
    （内部で mid にフォールバックしている想定）
    """
    base_ctx = {
        "fuji_status": {"risk": 0.1},
        "world": {"predicted_progress": 0.6},
        "value_ema": 0.6,
        "telos_weights": {"W_Transcendence": 0.6, "W_Struggle": 0.4},
    }

    ctx_mid = {**base_ctx, "time_horizon": "mid"}
    ctx_unknown = {**base_ctx, "time_horizon": "unknown"}

    s_mid = telos.telos_score(ctx_mid)
    s_unknown = telos.telos_score(ctx_unknown)

    assert math.isclose(s_mid, s_unknown, rel_tol=1e-6)


def test_telos_extreme_inputs_are_clamped_in_debug():
    """
    risk > 1 や progress < 0 など極端な入力が、
    telos_debug の input では 0..1 にクランプされていること。
    """
    ctx = {
        "fuji_status": {"risk": 2.0},          # >1 → 1.0 にクランプされる想定
        "world": {"predicted_progress": -1.0}, # <0 → 0.0 にクランプされる想定
        "value_ema": 1.5,                      # >1 → 1.0 にクランプされる想定
    }

    score = telos.telos_score(ctx)
    assert 0.0 <= score <= 1.0

    dbg = telos.telos_debug(ctx)

    assert 0.0 <= dbg["input"]["fuji_risk"] <= 1.0
    assert 0.0 <= dbg["input"]["world_predicted_progress"] <= 1.0
    assert 0.0 <= dbg["input"]["value_ema"] <= 1.0


def test_telos_debug_matches_telos_score_and_has_structure():
    """
    telos_debug の scores.final が telos_score と一致し、
    input/factors/scores のキー構造が期待どおりであること。
    """
    ctx = {
        "telos_weights": {"W_Transcendence": 0.6, "W_Struggle": 0.4},
        "time_horizon": "mid",
        "fuji_status": {"risk": 0.3},
        "world": {"predicted_progress": 0.7},
        "value_ema": 0.6,
    }

    debug = telos.telos_debug(ctx)
    score = telos.telos_score(ctx)

    assert "input" in debug
    assert "factors" in debug
    assert "scores" in debug

    assert "final" in debug["scores"]
    assert "base" in debug["scores"]
    assert "telos_weights" in debug["input"]
    assert debug["input"]["time_horizon"] == "mid"

    assert math.isclose(debug["scores"]["final"], score, rel_tol=1e-6)


def test_telos_weights_normalization_and_alias_keys():
    """
    telos_weights のキーが小文字 alias でも正しく読まれ、
    正規化後の重みが 2:1 の比率になること。
    """
    ctx = {"telos_weights": {"w_transcendence": 2.0, "w_struggle": 1.0}}

    debug = telos.telos_debug(ctx)
    wt = debug["input"]["telos_weights"]["W_Transcendence"]
    ws = debug["input"]["telos_weights"]["W_Struggle"]

    assert math.isclose(wt + ws, 1.0, rel_tol=1e-9)
    assert math.isclose(wt, 2.0 / 3.0, rel_tol=1e-9)
    assert math.isclose(ws, 1.0 / 3.0, rel_tol=1e-9)



