# tests/test_decision_status.py
"""
DecisionStatus Enum のテスト

NOTE: api/constants.py との整合性を保つため、BLOCK/ABSTAINを追加。
      REJECTEDは後方互換性のため維持。
"""
from veritas_os.core.decision_status import (
    DecisionStatus,
    DECISION_ALLOW,
    DECISION_MODIFY,
    DECISION_BLOCK,
    DECISION_ABSTAIN,
    DECISION_REJECTED,
    is_valid_status,
    normalize_status,
)


def test_enum_values_and_str():
    """Enum の値と __str__ が正しいこと"""
    assert DecisionStatus.ALLOW.value == "allow"
    assert DecisionStatus.MODIFY.value == "modify"
    assert DecisionStatus.BLOCK.value == "block"
    assert DecisionStatus.ABSTAIN.value == "abstain"
    assert DecisionStatus.REJECTED.value == "rejected"

    # __str__ が value を返すこと
    assert str(DecisionStatus.ALLOW) == "allow"
    assert str(DecisionStatus.MODIFY) == "modify"
    assert str(DecisionStatus.BLOCK) == "block"
    assert str(DecisionStatus.ABSTAIN) == "abstain"
    assert str(DecisionStatus.REJECTED) == "rejected"


def test_backward_compat_constants():
    """後方互換性のための文字列定数"""
    assert DECISION_ALLOW == "allow"
    assert DECISION_MODIFY == "modify"
    assert DECISION_BLOCK == "block"
    assert DECISION_ABSTAIN == "abstain"
    # REJECTED は後方互換性のため維持
    assert DECISION_REJECTED == "rejected"


def test_is_valid_status():
    """is_valid_status が正しく判定すること"""
    # 有効な値
    assert is_valid_status("allow") is True
    assert is_valid_status("modify") is True
    assert is_valid_status("block") is True
    assert is_valid_status("abstain") is True
    assert is_valid_status("rejected") is True  # 後方互換

    # 無効な値
    assert is_valid_status("unknown") is False
    assert is_valid_status("") is False
    assert is_valid_status("ALLOW") is False  # case-sensitive


def test_normalize_status_from_str():
    """文字列から DecisionStatus への変換"""
    assert normalize_status("allow") is DecisionStatus.ALLOW
    assert normalize_status("modify") is DecisionStatus.MODIFY
    assert normalize_status("block") is DecisionStatus.BLOCK
    assert normalize_status("abstain") is DecisionStatus.ABSTAIN
    assert normalize_status("rejected") is DecisionStatus.REJECTED


def test_normalize_status_from_enum():
    """Enum から Enum への変換（そのまま返す）"""
    assert normalize_status(DecisionStatus.MODIFY) is DecisionStatus.MODIFY
    assert normalize_status(DecisionStatus.BLOCK) is DecisionStatus.BLOCK


def test_normalize_status_invalid():
    """無効な値で ValueError が発生すること"""
    import pytest
    with pytest.raises(ValueError):
        normalize_status("invalid_status")
