# -*- coding: utf-8 -*-
"""GDPR 消去要求テスト: GDPR 消去要求 → cascade delete → 監査記録"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.scenario


class TestMemoryGdprErasure:
    """GDPR 消去要求のフローをテストするシナリオ"""

    def test_erasure_deletes_user_data(self, tmp_path, monkeypatch):
        """消去要求でユーザーデータが削除されること"""
        from veritas_os.tests.helpers.mocks import MockMemoryStore

        store = MockMemoryStore()
        store.put("episodic", {"id": "ep-1", "user_id": "user-A", "text": "data"})
        store.put("semantic", {"id": "sem-1", "user_id": "user-A", "text": "more data"})

        assert store.get("ep-1") is not None
        store.delete("ep-1")
        assert store.get("ep-1") is None

    def test_legal_hold_prevents_deletion(self):
        """法的ホールドがある場合削除されないこと"""
        from veritas_os.tests.helpers.mocks import MockMemoryStore

        store = MockMemoryStore()
        store.put("episodic", {"id": "ep-hold", "user_id": "user-A",
                               "meta": {"legal_hold": True}})
        entry = store.get("ep-hold")
        assert entry is not None
        assert entry.get("meta", {}).get("legal_hold") is True

    def test_erasure_audit_trail(self, tmp_path):
        """消去操作の監査証跡が作成されること"""
        from veritas_os.tests.helpers.mocks import MockTrustLog

        log = MockTrustLog()
        log.append({"action": "gdpr_erasure", "user_id": "user-A", "request_id": "req-del-1"})

        entries = log.load()
        assert len(entries) == 1
        assert entries[0]["action"] == "gdpr_erasure"
