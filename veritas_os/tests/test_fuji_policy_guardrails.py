# veritas_os/tests/test_fuji_policy_guardrails.py
from __future__ import annotations

import veritas_os.core.fuji as fuji


def test_trust_log_redacts_text_preview(monkeypatch):
    """
    TrustLog に書き込む text_preview から PII を赤化することを確認する。
    """
    captured: dict[str, dict] = {}

    def fake_append_trust_event(event: dict) -> None:
        captured["event"] = event

    monkeypatch.setattr(fuji, "append_trust_event", fake_append_trust_event)
    monkeypatch.setattr(
        fuji,
        "call_tool",
        lambda *args, **kwargs: {
            "ok": True,
            "risk_score": 0.1,
            "categories": [],
            "rationale": "",
            "model": "test",
        },
    )

    policy = dict(fuji._DEFAULT_POLICY)
    policy["blocked_keywords"] = {"hard_block": ["forbidden"], "sensitive": []}
    policy["audit"] = {"redact_before_log": True}
    policy["pii"] = {
        "enabled": True,
        "masked_markers": ["[redacted]"],
        "redact_kinds": {
            "phone": True,
            "email": True,
            "address_jp": True,
            "person_name_jp": False,
        },
    }
    monkeypatch.setattr(fuji, "POLICY", policy)

    text = "連絡先は090-1234-5678とtest@example.com、住所は東京都港区1-2-3です。"
    fuji.fuji_gate(text, context={}, evidence=[], alternatives=[])

    event = captured["event"]
    assert "090-1234-5678" not in event["text_preview"]
    assert "test@example.com" not in event["text_preview"]
    assert "東京都港区1-2-3" not in event["text_preview"]
    assert "[redacted]" in event["text_preview"]


def test_fallback_safety_head_uses_policy_keywords(monkeypatch):
    """
    fallback Safety Head が policy の blocked_keywords を参照することを確認。
    """
    policy = dict(fuji._DEFAULT_POLICY)
    policy["blocked_keywords"] = {
        "hard_block": ["forbiddenword"],
        "sensitive": ["sensitiveword"],
    }
    monkeypatch.setattr(fuji, "POLICY", policy)

    result = fuji._fallback_safety_head("forbiddenword")
    assert "illicit" in result.categories
    assert "forbiddenword" in result.rationale
