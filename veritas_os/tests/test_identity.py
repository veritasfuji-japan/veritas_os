# tests/test_identity.py

from veritas_os.core.identity import integrity_ok


def test_integrity_ok_returns_true_for_normal_title():
    assert integrity_ok("Option A") is True


def test_integrity_ok_returns_true_for_empty_title():
    # デモ実装なので空文字でも True のままであることを確認
    assert integrity_ok("") is True


def test_integrity_ok_returns_true_for_unicode_title():
    # 絵文字や日本語を含んでも問題なく True
    assert integrity_ok("⚙️ 安全モード / テスト") is True


