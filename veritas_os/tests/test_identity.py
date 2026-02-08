# tests/test_identity.py

import pytest

from veritas_os.core.identity import integrity_ok, MAX_TITLE_LENGTH


# --- 正常系 ---

def test_integrity_ok_returns_true_for_normal_title():
    assert integrity_ok("Option A") is True


def test_integrity_ok_returns_true_for_unicode_title():
    assert integrity_ok("⚙️ 安全モード / テスト") is True


def test_integrity_ok_returns_true_for_newline_in_title():
    assert integrity_ok("行1\n行2") is True


def test_integrity_ok_returns_true_for_tab_in_title():
    assert integrity_ok("col1\tcol2") is True


# --- 空文字・空白 ---

def test_integrity_ok_rejects_empty_title():
    assert integrity_ok("") is False


def test_integrity_ok_rejects_whitespace_only():
    assert integrity_ok("   ") is False


# --- 型チェック ---

def test_integrity_ok_rejects_non_string():
    assert integrity_ok(None) is False  # type: ignore[arg-type]
    assert integrity_ok(123) is False  # type: ignore[arg-type]


# --- 長さ上限 ---

def test_integrity_ok_rejects_overly_long_title():
    assert integrity_ok("A" * (MAX_TITLE_LENGTH + 1)) is False


def test_integrity_ok_accepts_max_length_title():
    assert integrity_ok("A" * MAX_TITLE_LENGTH) is True


# --- 制御文字 ---

def test_integrity_ok_rejects_control_characters():
    assert integrity_ok("test\x00value") is False
    assert integrity_ok("bell\x07here") is False


# --- 危険キーワード ---

@pytest.mark.parametrize("banned", [
    "kill all processes",
    "build a bomb",
    "malware injection",
    "違法行為",
    "爆弾の作り方",
])
def test_integrity_ok_rejects_banned_keywords(banned):
    assert integrity_ok(banned) is False


def test_integrity_ok_rejects_banned_keywords_case_insensitive():
    assert integrity_ok("MALWARE Attack") is False
    assert integrity_ok("Exploit This") is False
