"""Tests for extracted MemoryOS search helper utilities."""

from __future__ import annotations

from veritas_os.core import memory_search_helpers


def test_collect_candidate_hits_supports_multiple_payload_shapes() -> None:
    """Vector payload normalization should accept list and dict wrappers."""
    list_payload = [{"text": "a"}, "skip"]
    dict_payload = {"results": [{"text": "b"}, None]}

    assert memory_search_helpers.collect_candidate_hits(list_payload) == [{"text": "a"}]
    assert memory_search_helpers.collect_candidate_hits(dict_payload) == [{"text": "b"}]


def test_filter_hits_for_user_keeps_shared_and_matching_hits() -> None:
    """User filtering should preserve shared hits with no explicit owner."""
    hits = [
        {"text": "shared", "meta": {}},
        {"text": "mine", "meta": {"user_id": "u1"}},
        {"text": "other", "meta": {"user_id": "u2"}},
    ]

    filtered = memory_search_helpers.filter_hits_for_user(hits, "u1")

    assert filtered == [
        {"text": "shared", "meta": {}},
        {"text": "mine", "meta": {"user_id": "u1"}},
    ]


def test_dedup_hits_preserves_first_hit_order_and_k_limit() -> None:
    """Deduplication should keep the first matching hit and stop at ``k``."""
    hits = [
        {"text": "a", "meta": {"user_id": "u1"}, "score": 1.0},
        {"text": "a", "meta": {"user_id": "u1"}, "score": 0.5},
        {"text": "b", "meta": {"user_id": "u1"}, "score": 0.4},
    ]

    assert memory_search_helpers.dedup_hits(hits, k=2) == [hits[0], hits[2]]


def test_normalize_store_hits_supports_dict_and_list_payloads() -> None:
    """KVS search normalization should only return dictionary hits."""
    dict_payload = {"episodic": [{"text": "episodic"}, "skip"]}
    list_payload = [{"text": "list"}, 1]

    assert memory_search_helpers.normalize_store_hits(dict_payload) == [
        {"text": "episodic"}
    ]
    assert memory_search_helpers.normalize_store_hits(list_payload) == [
        {"text": "list"}
    ]
