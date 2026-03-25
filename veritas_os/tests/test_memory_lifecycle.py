"""Tests for memory lifecycle helper module."""

from __future__ import annotations

from veritas_os.core.memory_lifecycle import (
    is_record_expired,
    is_record_legal_hold,
    normalize_lifecycle,
    parse_expires_at,
    should_cascade_delete_semantic,
)


def test_parse_expires_at_invalid_returns_none() -> None:
    """Invalid date strings should fail closed to None."""
    assert parse_expires_at("not-a-date") is None


def test_parse_expires_at_parses_numeric_epoch_to_utc_iso() -> None:
    """Numeric epoch values should convert to UTC ISO-8601."""
    assert parse_expires_at(0) == "1970-01-01T00:00:00+00:00"


def test_parse_expires_at_parses_z_suffix_and_normalizes_timezone() -> None:
    """UTC Z suffix should be accepted and normalized."""
    assert parse_expires_at("2024-01-02T03:04:05Z") == "2024-01-02T03:04:05+00:00"


def test_parse_expires_at_blank_or_unsupported_returns_none() -> None:
    """Blank or unsupported payloads should fail closed."""
    assert parse_expires_at("   ") is None
    assert parse_expires_at({"expires_at": "2024-01-01"}) is None


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


def test_normalize_lifecycle_invalid_retention_class_falls_back_to_default() -> None:
    """Unknown retention class should be normalized to default."""
    result = normalize_lifecycle(
        value={"kind": "episode", "meta": {"retention_class": "INVALID"}},
        default_retention_class="standard",
        allowed_retention_classes={"short", "standard", "long", "regulated"},
        parse_expires_at_fn=parse_expires_at,
    )
    assert result["meta"]["retention_class"] == "standard"


def test_normalize_lifecycle_skips_non_memory_style_payload() -> None:
    """Payloads without memory keys should not be modified."""
    value = {"id": "raw-non-memory"}
    assert normalize_lifecycle(
        value=value,
        default_retention_class="standard",
        allowed_retention_classes={"short", "standard"},
        parse_expires_at_fn=parse_expires_at,
    ) == value


def test_is_record_expired_true_for_past_expiry_with_fixed_now() -> None:
    """Past expiry should mark record as expired using deterministic now."""
    record = {"value": {"meta": {"expires_at": "2024-01-01T00:00:00+00:00"}}}
    assert is_record_expired(
        record=record,
        parse_expires_at_fn=parse_expires_at,
        now_ts=1704067260.0,  # 2024-01-01T00:01:00+00:00
    )


def test_is_record_expired_false_for_future_expiry_with_fixed_now() -> None:
    """Future expiry should not mark record as expired."""
    record = {"value": {"meta": {"expires_at": "2024-01-01T00:02:00+00:00"}}}
    assert not is_record_expired(
        record=record,
        parse_expires_at_fn=parse_expires_at,
        now_ts=1704067260.0,  # 2024-01-01T00:01:00+00:00
    )


def test_is_record_expired_legal_hold_takes_precedence_over_expiry() -> None:
    """Legal hold must win over expiry state."""
    record = {
        "value": {
            "meta": {
                "expires_at": "2020-01-01T00:00:00+00:00",
                "legal_hold": True,
            }
        }
    }
    assert not is_record_expired(
        record=record,
        parse_expires_at_fn=parse_expires_at,
        now_ts=1704067260.0,
    )


def test_is_record_expired_malformed_record_handling() -> None:
    """Malformed record/meta structures should fail closed."""
    assert not is_record_expired(
        record={"value": "not-a-dict"},
        parse_expires_at_fn=parse_expires_at,
        now_ts=1704067260.0,
    )
    assert not is_record_expired(
        record={"value": {"meta": "not-a-dict"}},
        parse_expires_at_fn=parse_expires_at,
        now_ts=1704067260.0,
    )


def test_is_record_legal_hold_true_and_false_paths() -> None:
    """Legal hold helper should handle positive and malformed inputs."""
    assert is_record_legal_hold({"value": {"meta": {"legal_hold": True}}})
    assert not is_record_legal_hold({"value": {"meta": {"legal_hold": False}}})
    assert not is_record_legal_hold({"value": {"meta": "invalid"}})


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


def test_should_cascade_delete_semantic_negative_paths() -> None:
    """Cascade delete should be denied for non-eligible records."""
    base = {
        "value": {
            "kind": "semantic",
            "meta": {
                "user_id": "u1",
                "source_episode_keys": ["ep-1"],
                "legal_hold": False,
            },
        }
    }

    assert not should_cascade_delete_semantic(
        record=base,
        user_id="u1",
        erased_keys=set(),
    )
    assert not should_cascade_delete_semantic(
        record={"value": {"kind": "episodic", "meta": base["value"]["meta"]}},
        user_id="u1",
        erased_keys={"ep-1"},
    )
    assert not should_cascade_delete_semantic(
        record={"value": {"kind": "semantic", "meta": {"user_id": "u2"}}},
        user_id="u1",
        erased_keys={"ep-1"},
    )
    assert not should_cascade_delete_semantic(
        record={
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["ep-1"],
                    "legal_hold": True,
                },
            }
        },
        user_id="u1",
        erased_keys={"ep-1"},
    )
    assert not should_cascade_delete_semantic(
        record={
            "value": {
                "kind": "semantic",
                "meta": {"user_id": "u1", "source_episode_keys": "ep-1"},
            }
        },
        user_id="u1",
        erased_keys={"ep-1"},
    )
