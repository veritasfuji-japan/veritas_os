# veritas_os/tests/test_api_constants.py
from __future__ import annotations

import pytest

from veritas_os.api.constants import (
    DecisionStatus,
    DECISION_ALLOW,
    DECISION_MODIFY,
    DECISION_BLOCK,
    DECISION_ABSTAIN,
    DECISION_REJECTED,
    is_valid_status,
    normalize_status,
)


def test_decision_status_enum_values_and_str():
    # Enum の value と __str__ が期待通りか
    assert DecisionStatus.ALLOW.value == "allow"
    assert DecisionStatus.MODIFY.value == "modify"
    assert DecisionStatus.BLOCK.value == "block"
    assert DecisionStatus.ABSTAIN.value == "abstain"
    assert DecisionStatus.REJECTED.value == "rejected"

    # __str__ は value を返す
    assert str(DecisionStatus.ALLOW) == "allow"
    assert str(DecisionStatus.MODIFY) == "modify"
    assert str(DecisionStatus.BLOCK) == "block"
    assert str(DecisionStatus.ABSTAIN) == "abstain"
    assert str(DecisionStatus.REJECTED) == "rejected"


def test_backward_compat_string_constants():
    # 文字列定数が Enum の値と一致しているか
    assert DECISION_ALLOW == DecisionStatus.ALLOW.value
    assert DECISION_MODIFY == DecisionStatus.MODIFY.value
    assert DECISION_BLOCK == DecisionStatus.BLOCK.value
    assert DECISION_ABSTAIN == DecisionStatus.ABSTAIN.value

    # 旧名（rejected）は後方互換性のために維持
    assert DECISION_REJECTED == DecisionStatus.REJECTED.value


def test_is_valid_status():
    # 有効なステータスは True
    for s in ["allow", "modify", "block", "abstain", "rejected"]:
        assert is_valid_status(s) is True

    # 無効なステータスは False（except パスも踏む）
    for s in ["invalid", "", "ALLOW", "reject"]:
        assert is_valid_status(s) is False


def test_normalize_status_from_str_and_enum():
    # 文字列 → Enum に正しく変換される
    assert normalize_status("allow") is DecisionStatus.ALLOW
    assert normalize_status("modify") is DecisionStatus.MODIFY
    assert normalize_status("block") is DecisionStatus.BLOCK
    assert normalize_status("abstain") is DecisionStatus.ABSTAIN
    assert normalize_status("rejected") is DecisionStatus.REJECTED

    # すでに Enum の場合はそのまま返る（if 分岐）
    st = DecisionStatus.ALLOW
    assert normalize_status(st) is st


def test_normalize_status_invalid_raises():
    # 不正な文字列は ValueError になる（DecisionStatus(status) 側の例外パス）
    with pytest.raises(ValueError):
        normalize_status("invalid_status")

