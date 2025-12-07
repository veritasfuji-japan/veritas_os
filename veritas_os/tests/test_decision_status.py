# tests/test_decision_status.py
from veritas_os.core.decision_status import (
    DecisionStatus,
    DECISION_ALLOW,
    DECISION_MODIFY,
    DECISION_REJECTED,
    is_valid_status,
    normalize_status,
)


def test_enum_values_and_str():
    assert DecisionStatus.ALLOW.value == "allow"
    assert DecisionStatus.MODIFY.value == "modify"
    assert DecisionStatus.REJECTED.value == "rejected"

    # __str__ が value を返すこと
    assert str(DecisionStatus.ALLOW) == "allow"


def test_backward_compat_constants():
    assert DECISION_ALLOW == "allow"
    assert DECISION_MODIFY == "modify"
    assert DECISION_REJECTED == "rejected"


def test_is_valid_status():
    assert is_valid_status("allow") is True
    assert is_valid_status("modify") is True
    assert is_valid_status("rejected") is True
    assert is_valid_status("unknown") is False
    assert is_valid_status("") is False


def test_normalize_status_from_str():
    s = normalize_status("allow")
    assert isinstance(s, DecisionStatus)
    assert s is DecisionStatus.ALLOW


def test_normalize_status_from_enum():
    s = normalize_status(DecisionStatus.MODIFY)
    assert s is DecisionStatus.MODIFY

