"""Tests for extracted MemoryOS helper utilities."""

from __future__ import annotations

from veritas_os.core import memory_helpers


class _ResponseObject:
    """Simple response stub exposing a text attribute."""

    def __init__(self, text: str) -> None:
        self.text = text


def test_collect_episodic_records_filters_and_sorts() -> None:
    """Only episodic records that match the tag filter should remain."""
    records = [
        {
            "key": "episode_old",
            "ts": 10,
            "value": {"kind": "episodic", "text": "older note", "tags": ["ops"]},
        },
        {
            "key": "semantic_1",
            "ts": 11,
            "value": {"kind": "semantic", "text": "ignore me", "tags": ["ops"]},
        },
        {
            "key": "episode_new",
            "ts": 20,
            "value": {"kind": "episodic", "text": "newer note", "tags": ["ops", "p1"]},
        },
    ]

    episodic = memory_helpers.collect_episodic_records(
        records,
        min_text_len=5,
        tags=["p1"],
    )

    assert [item["source_key"] for item in episodic] == ["episode_new"]


def test_extract_summary_text_supports_choice_payload() -> None:
    """Choice-style LLM payloads should still be parsed after extraction."""
    response = {"choices": [{"message": {"content": "  summary  "}}]}

    assert memory_helpers.extract_summary_text(response) == "summary"


def test_extract_summary_text_supports_text_attribute() -> None:
    """Attribute-style SDK responses should still be supported."""
    assert memory_helpers.extract_summary_text(_ResponseObject("done")) == "done"


def test_build_vector_rebuild_documents_merges_record_metadata() -> None:
    """Vector rebuild docs must preserve record/user metadata for traceability."""
    records = [
        {
            "user_id": "user-1",
            "ts": 123,
            "value": {
                "kind": "episodic",
                "text": "indexed text",
                "tags": ["tag"],
                "meta": {"source": "manual"},
            },
        }
    ]

    documents = memory_helpers.build_vector_rebuild_documents(records)

    assert documents == [
        {
            "kind": "episodic",
            "text": "indexed text",
            "tags": ["tag"],
            "meta": {
                "user_id": "user-1",
                "created_at": 123,
                "source": "manual",
            },
        }
    ]
