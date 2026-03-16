# tests for veritas_os/core/memory_compliance.py
"""Tests for GDPR user-erasure compliance helpers."""
from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from veritas_os.core.memory_compliance import (
    erase_user_data,
    is_record_legal_hold,
    should_cascade_delete_semantic,
)


# ---------------------------------------------------------------------------
# is_record_legal_hold
# ---------------------------------------------------------------------------

class TestIsRecordLegalHold:
    def test_true_when_legal_hold_set(self):
        record = {"value": {"meta": {"legal_hold": True}}}
        assert is_record_legal_hold(record) is True

    def test_false_when_not_set(self):
        record = {"value": {"meta": {"legal_hold": False}}}
        assert is_record_legal_hold(record) is False

    def test_false_when_no_meta(self):
        record = {"value": {}}
        assert is_record_legal_hold(record) is False

    def test_false_when_value_not_dict(self):
        record = {"value": "string_value"}
        assert is_record_legal_hold(record) is False

    def test_false_when_meta_not_dict(self):
        record = {"value": {"meta": "not_dict"}}
        assert is_record_legal_hold(record) is False

    def test_false_when_no_value(self):
        record = {}
        assert is_record_legal_hold(record) is False

    def test_false_when_value_is_none(self):
        record = {"value": None}
        assert is_record_legal_hold(record) is False


# ---------------------------------------------------------------------------
# should_cascade_delete_semantic
# ---------------------------------------------------------------------------

class TestShouldCascadeDeleteSemantic:
    def _semantic_record(self, user_id: str, source_keys: list) -> dict:
        return {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": user_id,
                    "source_episode_keys": source_keys,
                },
            }
        }

    def test_cascade_when_source_key_erased(self):
        record = self._semantic_record("u1", ["k1", "k2"])
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is True

    def test_no_cascade_when_no_erased_keys(self):
        record = self._semantic_record("u1", ["k1"])
        assert should_cascade_delete_semantic(record, "u1", set()) is False

    def test_no_cascade_when_different_user(self):
        record = self._semantic_record("u1", ["k1"])
        assert should_cascade_delete_semantic(record, "u2", {"k1"}) is False

    def test_no_cascade_when_not_semantic(self):
        record = {"value": {"kind": "episodic", "meta": {"user_id": "u1", "source_episode_keys": ["k1"]}}}
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_when_legal_hold(self):
        record = {
            "value": {
                "kind": "semantic",
                "meta": {
                    "user_id": "u1",
                    "source_episode_keys": ["k1"],
                    "legal_hold": True,
                },
            }
        }
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_when_value_not_dict(self):
        record = {"value": "string"}
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_when_meta_not_dict(self):
        record = {"value": {"kind": "semantic", "meta": "bad"}}
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_when_source_keys_not_list(self):
        record = {"value": {"kind": "semantic", "meta": {"user_id": "u1", "source_episode_keys": "not_list"}}}
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False

    def test_no_cascade_when_source_keys_not_overlapping(self):
        record = self._semantic_record("u1", ["k3", "k4"])
        assert should_cascade_delete_semantic(record, "u1", {"k1"}) is False


# ---------------------------------------------------------------------------
# erase_user_data
# ---------------------------------------------------------------------------

class TestEraseUserData:
    def _make_record(self, user_id: str, key: str, **extra_value) -> dict:
        return {
            "user_id": user_id,
            "key": key,
            "value": extra_value or {"text": "hello"},
            "ts": time.time(),
        }

    def test_erases_user_records(self):
        data = [
            self._make_record("u1", "k1"),
            self._make_record("u2", "k2"),
        ]
        kept, report = erase_user_data(data, "u1", "gdpr", "admin")
        # u1's record deleted, u2 remains, plus audit record
        user_keys = [r["key"] for r in kept if r["user_id"] != "__audit__"]
        assert "k1" not in user_keys
        assert "k2" in user_keys
        assert report["deleted_count"] == 1

    def test_legal_hold_prevents_deletion(self):
        data = [
            {
                "user_id": "u1",
                "key": "k1",
                "value": {"meta": {"legal_hold": True}},
                "ts": time.time(),
            }
        ]
        kept, report = erase_user_data(data, "u1", "gdpr", "admin")
        assert report["protected_by_legal_hold"] == 1
        assert report["deleted_count"] == 0
        # record is kept (plus audit)
        non_audit = [r for r in kept if r["user_id"] != "__audit__"]
        assert len(non_audit) == 1

    def test_cascade_deletes_semantic(self):
        data = [
            self._make_record("u1", "k1"),  # will be deleted
            {
                "user_id": "u1",
                "key": "sem1",
                "value": {
                    "kind": "semantic",
                    "meta": {
                        "user_id": "u1",
                        "source_episode_keys": ["k1"],
                    },
                },
                "ts": time.time(),
            },
        ]
        kept, report = erase_user_data(data, "u1", "gdpr", "admin")
        assert report["cascade_deleted_count"] == 1

    def test_audit_record_appended(self):
        data = [self._make_record("u1", "k1")]
        kept, report = erase_user_data(data, "u1", "gdpr", "admin")
        audit = [r for r in kept if r["user_id"] == "__audit__"]
        assert len(audit) == 1
        assert audit[0]["value"]["kind"] == "audit"
        assert report["reason"] == "gdpr"
        assert report["actor"] == "admin"

    def test_no_records_for_user(self):
        data = [self._make_record("u2", "k1")]
        kept, report = erase_user_data(data, "u1", "gdpr", "admin")
        assert report["deleted_count"] == 0
        # u2 record + audit
        assert len(kept) == 2
