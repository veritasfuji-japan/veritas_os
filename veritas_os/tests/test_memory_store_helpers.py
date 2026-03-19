"""Tests for extracted MemoryStore helper utilities."""

from __future__ import annotations

from veritas_os.core import memory_store_helpers


def test_filter_recent_records_sorts_and_filters_dict_values() -> None:
    """Recent filtering should preserve recency while matching query/text fields."""
    records = [
        {"ts": 10, "value": {"text": "older note"}},
        {"ts": 20, "value": {"query": "find newest"}},
        {"ts": 15, "value": "plain text value"},
    ]

    filtered = memory_store_helpers.filter_recent_records(
        records,
        contains="new",
        limit=5,
    )

    assert filtered == [{"ts": 20, "value": {"query": "find newest"}}]


def test_simple_score_returns_partial_and_token_overlap_signal() -> None:
    """Fallback scoring should remain stable for substring and token overlap."""
    score = memory_store_helpers.simple_score(
        "alpha beta",
        "alpha beta memo",
    )

    assert score == 1.0


def test_build_kvs_search_hits_applies_user_kind_and_similarity_filters() -> None:
    """KVS hit building must preserve existing fail-closed filtering behavior."""
    records = [
        {
            "key": "keep",
            "user_id": "u1",
            "ts": 30,
            "value": {
                "text": "incident response playbook",
                "tags": ["ops"],
                "kind": "episodic",
            },
        },
        {
            "key": "drop-kind",
            "user_id": "u1",
            "ts": 20,
            "value": {"text": "incident response", "kind": "semantic"},
        },
        {
            "key": "drop-user",
            "user_id": "u2",
            "ts": 10,
            "value": {"text": "incident response", "kind": "episodic"},
        },
    ]

    hits = memory_store_helpers.build_kvs_search_hits(
        records,
        query="incident response",
        k=5,
        kinds=["episodic"],
        min_sim=0.4,
        user_id="u1",
    )

    assert hits == [
        {
            "id": "keep",
            "text": "incident response playbook",
            "score": 1.0,
            "tags": ["ops"],
            "ts": 30,
            "meta": {
                "user_id": "u1",
                "created_at": 30,
                "kind": "episodic",
            },
        }
    ]
