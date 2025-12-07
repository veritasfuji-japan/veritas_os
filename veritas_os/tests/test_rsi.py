# veritas_os/tests/test_rsi.py
from __future__ import annotations

from veritas_os.core import rsi


def test_propose_patch_basic():
    """propose_patch が決め打ちのパッチを返すことだけ確認。"""
    last_outcome = {"dummy": "value"}
    patch = rsi.propose_patch(last_outcome)

    assert patch["min_evidence_delta"] == 1
    assert patch["critique_weight_delta"] == 0.1
    # キーのセットも明示的にチェック
    assert set(patch.keys()) == {"min_evidence_delta", 
"critique_weight_delta"}


def test_validate_and_apply_on_empty_state_uses_defaults_and_patch():
    """
    state が空のとき:
    - kernel が自動で作られる
    - デフォルト値 + パッチ分が入る
    """
    state = {}
    patch = {
        "min_evidence_delta": 1,
        "critique_weight_delta": 0.1,
    }

    new_state = rsi.validate_and_apply(patch, state)

    assert "kernel" in new_state
    k = new_state["kernel"]

    # min_evidence は DEFAULT_MIN_EVIDENCE に +1
    assert k["min_evidence"] == rsi.DEFAULT_MIN_EVIDENCE + 1

    # critique_weight は DEFAULT_CRITIQUE_WEIGHT に +0.1 （小数2桁に丸め）
    expected_cw = round(rsi.DEFAULT_CRITIQUE_WEIGHT + 0.1, 2)
    assert k["critique_weight"] == expected_cw


def test_validate_and_apply_clips_to_max_bounds():
    """
    上限越えのパッチは MAX_* でクリップされる。
    """
    state = {"kernel": {}}
    patch = {
        "min_evidence_delta": 999,      # 明らかに大きい値
        "critique_weight_delta": 999.0,
    }

    new_state = rsi.validate_and_apply(patch, state)
    k = new_state["kernel"]

    assert k["min_evidence"] == rsi.MAX_MIN_EVIDENCE
    assert k["critique_weight"] == rsi.MAX_CRITIQUE_WEIGHT


def test_validate_and_apply_clips_to_min_bounds():
    """
    下限より小さくなるパッチは MIN_* でクリップされる。
    """
    state = {
        "kernel": {
            "min_evidence": rsi.MIN_MIN_EVIDENCE,
            "critique_weight": rsi.MIN_CRITIQUE_WEIGHT,
        }
    }
    patch = {
        "min_evidence_delta": -999,     # 大きくマイナス
        "critique_weight_delta": -999.0,
    }

    new_state = rsi.validate_and_apply(patch, state)
    k = new_state["kernel"]

    assert k["min_evidence"] == rsi.MIN_MIN_EVIDENCE
    assert k["critique_weight"] == rsi.MIN_CRITIQUE_WEIGHT


def test_validate_and_apply_ignores_invalid_patch_values():
    """
    patch に数値変換できない値が入っていても例外にならず、
    delta は 0 として扱われる（= 現在値は維持される）。
    """
    state = {
        "kernel": {
            "min_evidence": 3,
            "critique_weight": 1.23,
        }
    }
    patch = {
        "min_evidence_delta": "not-a-number",
        "critique_weight_delta": object(),
    }

    new_state = rsi.validate_and_apply(patch, state)
    k = new_state["kernel"]

    # 変化しないことを確認
    assert k["min_evidence"] == 3
    assert k["critique_weight"] == 1.23

