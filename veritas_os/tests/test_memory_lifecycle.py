"""Tests for memory lifecycle helper module."""

from __future__ import annotations

import time

from veritas_os.core.memory_lifecycle import (
    is_record_expired,
    normalize_lifecycle,
    parse_expires_at,
    should_cascade_delete_semantic,
)


def test_parse_expires_at_invalid_returns_none() -> None:
    """Invalid date strings should fail closed to None."""
    assert parse_expires_at("not-a-date") is None


def test_normalize_lifecycle_defaults_retention_and_hold() -> None:
    """Lifecycle defaults should be attached to memory-style documents."""
    result = normalize_lifecycle(
        value={"text": "hello", "meta": {}},
        default_retention_class="standard",
        allowed_retention_classes={"short", "standard", "long", "regulated"},
        parse_expires_at_fn=parse_expires_at,
    )
    assert result["meta"]["retention_class"] == "standard"
    assert result["meta"]["legal_hold"] is False


def test_is_record_expired_true_for_past_timestamp() -> None:
    """Past expiry timestamp should mark record as expired."""
    record = {"value": {"meta": {"expires_at": time.time() - 60}}}
    assert (
        is_record_expired(
            record=record,
            parse_expires_at_fn=parse_expires_at,
        )
        is True
    )


def test_should_cascade_delete_semantic_checks_lineage() -> None:
    """Semantic records sourced from erased episodes should be cascade deleted."""
    semantic_record = {
        "value": {
            "kind": "semantic",
            "meta": {
                "user_id": "u1",
                "source_episode_keys": ["ep-1", "ep-2"],
                "legal_hold": False,
            },
        }
    }
    assert (
        should_cascade_delete_semantic(
            record=semantic_record,
            user_id="u1",
            erased_keys={"ep-2"},
        )
        is True
    )
