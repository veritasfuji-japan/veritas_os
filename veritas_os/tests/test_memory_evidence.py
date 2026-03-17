from __future__ import annotations

from typing import Any, Dict, List

from veritas_os.core import memory_evidence as evidence


def test_hits_to_evidence_filters_invalid_records() -> None:
    hits: List[Dict[str, Any]] = [
        {"id": "1", "text": "hello", "score": 0.4},
        {"id": "2", "text": ""},
    ]

    result = evidence.hits_to_evidence(hits, source_prefix="mem")

    assert result == [
        {
            "source": "mem:1",
            "text": "hello",
            "score": 0.4,
            "tags": [],
            "meta": {},
        }
    ]


def test_get_evidence_for_decision_uses_search_and_context_user() -> None:
    captured: Dict[str, Any] = {}

    def fake_search_fn(*, query: str, k: int, user_id: str) -> List[Dict[str, Any]]:
        captured.update({"query": query, "k": k, "user_id": user_id})
        return [{"id": "x", "text": "evidence"}]

    decision = {"chosen": {"title": "Need contract review"}, "context": {"user_id": "u-1"}}
    result = evidence.get_evidence_for_decision(decision, search_fn=fake_search_fn, top_k=3)

    assert captured == {"query": "Need contract review", "k": 3, "user_id": "u-1"}
    assert result[0]["source"] == "memory:x"


def test_get_evidence_for_query_ignores_empty_query() -> None:
    def fail_search_fn(**_: Any) -> List[Dict[str, Any]]:
        raise AssertionError("should not be called")

    assert evidence.get_evidence_for_query("  ", search_fn=fail_search_fn) == []
