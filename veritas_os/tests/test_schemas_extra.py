# veritas_os/tests/test_schemas_extra.py
"""Additional tests for schemas.py to improve coverage."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from veritas_os.api import schemas as schemas_mod


class TestAsListHelper:
    """Tests for _as_list helper function."""

    def test_none_returns_empty_list(self):
        """None should return empty list."""
        assert schemas_mod._as_list(None) == []

    def test_list_returns_same_list(self):
        """List should be returned as-is."""
        result = schemas_mod._as_list([1, 2, 3])
        assert result == [1, 2, 3]

    def test_dict_returns_list_with_dict(self):
        """Dict should be wrapped in a list."""
        result = schemas_mod._as_list({"key": "value"})
        assert result == [{"key": "value"}]

    def test_scalar_string_returns_list(self):
        """Scalar string should be wrapped in list."""
        assert schemas_mod._as_list("hello") == ["hello"]

    def test_scalar_int_returns_list(self):
        """Scalar int should be wrapped in list."""
        assert schemas_mod._as_list(42) == [42]

    def test_scalar_float_returns_list(self):
        """Scalar float should be wrapped in list."""
        assert schemas_mod._as_list(3.14) == [3.14]

    def test_scalar_bool_returns_list(self):
        """Scalar bool should be wrapped in list."""
        assert schemas_mod._as_list(True) == [True]

    def test_tuple_converted_to_list(self):
        """Tuple should be converted to list."""
        result = schemas_mod._as_list((1, 2, 3))
        assert result == [1, 2, 3]

    def test_set_converted_to_list(self):
        """Set should be converted to list."""
        result = schemas_mod._as_list({1, 2, 3})
        assert sorted(result) == [1, 2, 3]

    def test_generator_converted_to_list(self):
        """Generator should be converted to list."""
        gen = (x for x in [1, 2, 3])
        result = schemas_mod._as_list(gen)
        assert result == [1, 2, 3]


class TestCoerceContext:
    """Tests for _coerce_context helper function."""

    def test_none_returns_empty_dict(self):
        """None should return empty dict."""
        assert schemas_mod._coerce_context(None) == {}

    def test_context_model_dumped(self):
        """Context model should be dumped to dict."""
        ctx = schemas_mod.Context(user_id="user1", query="test")
        result = schemas_mod._coerce_context(ctx)
        assert result["user_id"] == "user1"
        assert result["query"] == "test"

    def test_dict_returned_as_dict(self):
        """Dict should be returned as dict."""
        result = schemas_mod._coerce_context({"key": "value"})
        assert result == {"key": "value"}

    def test_non_mapping_wrapped_in_raw(self):
        """Non-mapping value should be wrapped in 'raw' key."""
        result = schemas_mod._coerce_context("some string")
        assert result == {"raw": "some string"}


class TestContextModel:
    """Tests for Context model."""

    def test_basic_creation(self):
        """Context should be creatable with required fields."""
        ctx = schemas_mod.Context(user_id="user1", query="test query")
        assert ctx.user_id == "user1"
        assert ctx.query == "test query"

    def test_optional_fields(self):
        """Optional fields should be settable."""
        ctx = schemas_mod.Context(
            user_id="user1",
            query="test",
            goals=["goal1", "goal2"],
            constraints=["limit1"],
            time_horizon="short",
        )
        assert ctx.goals == ["goal1", "goal2"]
        assert ctx.constraints == ["limit1"]
        assert ctx.time_horizon == "short"

    def test_extra_fields_allowed(self):
        """Extra fields should be allowed."""
        ctx = schemas_mod.Context(
            user_id="user1",
            query="test",
            custom_field="custom_value"
        )
        assert ctx.model_extra.get("custom_field") == "custom_value"


class TestDecideRequest:
    """Tests for DecideRequest model."""

    def test_basic_creation(self):
        """DecideRequest should be creatable."""
        req = schemas_mod.DecideRequest(
            query="test query",
            user_id="user1",
        )
        assert req.query == "test query"
        assert req.user_id == "user1"

    def test_with_options(self):
        """DecideRequest with options."""
        req = schemas_mod.DecideRequest(
            query="test",
            user_id="user1",
            options=[{"title": "Option 1"}, {"title": "Option 2"}],
        )
        assert len(req.options) == 2

    def test_with_evidence(self):
        """DecideRequest with evidence."""
        req = schemas_mod.DecideRequest(
            query="test",
            user_id="user1",
            evidence=[{"snippet": "evidence 1"}],
        )
        assert len(req.evidence) == 1


class TestDecideResponse:
    """Tests for DecideResponse model."""

    def test_basic_creation(self):
        """DecideResponse should be creatable."""
        resp = schemas_mod.DecideResponse(
            request_id="req1",
            decision_id="dec1",
            answer="Test answer",
        )
        assert resp.request_id == "req1"
        assert resp.answer == "Test answer"


class TestOption:
    """Tests for Option model if it exists."""

    def test_option_creation(self):
        """Option model should be creatable."""
        if hasattr(schemas_mod, "Option"):
            opt = schemas_mod.Option(title="Test Option")
            assert opt.title == "Test Option"


class TestEvidence:
    """Tests for Evidence model if it exists."""

    def test_evidence_creation(self):
        """Evidence model should be creatable."""
        if hasattr(schemas_mod, "Evidence"):
            ev = schemas_mod.Evidence(snippet="Test snippet")
            assert ev.snippet == "Test snippet"


class TestIsMapping:
    """Tests for _is_mapping helper."""

    def test_dict_is_mapping(self):
        """Dict should be considered mapping."""
        assert schemas_mod._is_mapping({}) is True
        assert schemas_mod._is_mapping({"a": 1}) is True

    def test_non_dict_not_mapping(self):
        """Non-dict should not be considered mapping."""
        assert schemas_mod._is_mapping([]) is False
        assert schemas_mod._is_mapping("string") is False
        assert schemas_mod._is_mapping(123) is False
        assert schemas_mod._is_mapping(None) is False
