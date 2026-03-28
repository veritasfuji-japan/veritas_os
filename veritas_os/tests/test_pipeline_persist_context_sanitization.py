"""Tests for context sanitization in pipeline persistence."""

from __future__ import annotations

from veritas_os.core import pipeline_persist


def test_compact_world_state_keeps_only_current_user() -> None:
    world_state = {
        "schema_version": "2.0.0",
        "updated_at": "2026-03-28T00:00:00+00:00",
        "meta": {
            "version": "2.0",
            "created_at": "2025-12-01T00:00:00+00:00",
            "repo_fingerprint": "abc123",
            "last_users": {
                "u1": {"last_seen": "2026-03-28T00:00:00+00:00"},
                "legacy": {"last_seen": "2025-01-01T00:00:00+00:00"},
            },
        },
        "projects": [
            {"project_id": "u1:default", "owner_user_id": "u1", "title": "U1"},
            {"project_id": "legacy:default", "owner_user_id": "legacy", "title": "Legacy"},
        ],
        "history": {"decisions": [{"chosen_title": "old"}]},
        "veritas": {"decision_count": 10},
        "metrics": {"value_ema": 0.5},
    }

    compact = pipeline_persist._compact_world_state_for_persist(world_state, "u1")

    assert list(compact["meta"]["last_users"].keys()) == ["u1"]
    assert len(compact["projects"]) == 1
    assert compact["projects"][0]["owner_user_id"] == "u1"
    assert "history" not in compact


def test_sanitize_context_removes_heavy_keys() -> None:
    context = {
        "user_id": "u1",
        "world_state": {
            "schema_version": "2.0.0",
            "meta": {"last_users": {"u1": {}, "legacy": {}}},
            "projects": [{"owner_user_id": "u1"}, {"owner_user_id": "legacy"}],
        },
        "projects": [{"id": "should-be-removed"}],
        "history": {"decisions": [{"id": "old"}]},
        "fast": False,
    }

    safe = pipeline_persist._sanitize_context_for_persist(context, "u1")

    assert "projects" not in safe
    assert "history" not in safe
    assert safe["world_state"]["meta"]["last_users"] == {"u1": {}}
    assert safe["fast"] is False
