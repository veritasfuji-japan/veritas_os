# -*- coding: utf-8 -*-
"""Continuation Runtime 再検証フローテスト"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.scenario


class TestContinuationChain:
    """Continuation Runtime の再検証フローをテストするシナリオ"""

    def test_continuation_triggers_revalidation(self, monkeypatch):
        """Continuation が再検証をトリガーすること"""
        from veritas_os.core import fuji

        monkeypatch.setattr(fuji, "call_tool", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no tool")))
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: None)

        first = fuji.fuji_gate("初回判定クエリ")
        assert "status" in first

        second = fuji.fuji_gate("継続判定クエリ")
        assert "status" in second

    def test_chain_of_decisions_produces_results(self, monkeypatch):
        """連続判定がそれぞれ結果を返すこと"""
        from veritas_os.core import fuji

        events = []
        monkeypatch.setattr(fuji, "call_tool", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no tool")))
        monkeypatch.setattr(fuji, "append_trust_event", lambda e: events.append(e))

        for i in range(3):
            result = fuji.fuji_gate(f"判定クエリ {i}")
            assert "risk" in result
            assert "decision_status" in result

        assert len(events) == 3
