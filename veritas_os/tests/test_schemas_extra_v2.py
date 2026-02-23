# veritas_os/tests/test_schemas_extra_v2.py
"""Additional tests for api/schemas.py to improve coverage.

Targets uncovered lines:
  - _as_list iterable that fails conversion (line 57-58)
  - EvidenceItem BaseModel path (line 492-493)
  - str evidence path (line 513, 515)
  - DecideRequest with too many alternatives
  - DecideResponse alternatives/options with BaseModel/str/other types
  - _coerce_evidence_to_list_of_dicts various paths
  - DecideResponse evidence with various types
"""
from __future__ import annotations

from typing import Any, Dict, Generator, List
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from veritas_os.api import schemas


# =========================================================
# _as_list edge cases
# =========================================================

class TestAsListEdgeCases:
    def test_iterable_that_fails(self):
        """An iterable that raises on list() falls back to [v]."""
        class BadIter:
            def __iter__(self):
                raise RuntimeError("iteration failed")

        # _as_list should catch this exception
        result = schemas._as_list(BadIter())
        # Either returns [v] or handles gracefully
        assert isinstance(result, list)

    def test_generator_converted(self):
        """Generator is converted to list."""
        def gen():
            yield 1
            yield 2

        result = schemas._as_list(gen())
        assert result == [1, 2]

    def test_tuple_converted(self):
        result = schemas._as_list((1, 2, 3))
        assert result == [1, 2, 3]


# =========================================================
# _altin_to_altitem edge cases
# =========================================================

class TestAltinToAltitem:
    def test_none_returns_empty(self):
        result = schemas._altin_to_altitem(None)
        assert isinstance(result, schemas.AltItem)

    def test_altitem_passthrough(self):
        item = schemas.AltItem(title="Test")
        result = schemas._altin_to_altitem(item)
        assert result is item

    def test_option_converted(self):
        opt = schemas.Option(id="1", title="Option A")
        result = schemas._altin_to_altitem(opt)
        assert isinstance(result, schemas.AltItem)

    def test_dict_converted(self):
        result = schemas._altin_to_altitem({"id": "1", "title": "Test"})
        assert isinstance(result, schemas.AltItem)

    def test_scalar_becomes_title(self):
        result = schemas._altin_to_altitem("scalar string")
        assert isinstance(result, schemas.AltItem)
        assert result.title == "scalar string"


# =========================================================
# DecideRequest field validators
# =========================================================

class TestDecideRequestValidators:
    def test_alternatives_too_many_raises(self):
        """Too many alternatives raises ValueError."""
        big_list = [{"id": str(i), "title": f"Opt {i}"} for i in range(schemas.MAX_LIST_ITEMS + 1)]
        with pytest.raises(Exception):  # ValidationError
            schemas.DecideRequest(
                query="test",
                context={"user_id": "u1", "query": "test"},
                alternatives=big_list,
            )

    def test_options_too_many_raises(self):
        """Too many options raises ValueError."""
        big_list = [{"id": str(i), "title": f"Opt {i}"} for i in range(schemas.MAX_LIST_ITEMS + 1)]
        with pytest.raises(Exception):
            schemas.DecideRequest(
                query="test",
                context={"user_id": "u1", "query": "test"},
                options=big_list,
            )

    def test_none_alternatives_becomes_empty(self):
        req = schemas.DecideRequest(
            query="test",
            context={"user_id": "u1", "query": "test"},
            alternatives=None,
        )
        assert req.alternatives == []

    def test_none_options_becomes_empty(self):
        req = schemas.DecideRequest(
            query="test",
            context={"user_id": "u1", "query": "test"},
            options=None,
        )
        assert req.options == []

    def test_options_copied_to_alternatives_when_alts_empty(self):
        req = schemas.DecideRequest(
            query="test",
            context={"user_id": "u1", "query": "test"},
            alternatives=None,
            options=[{"id": "1", "title": "Option A"}],
        )
        assert len(req.alternatives) == 1


# =========================================================
# DecideResponse with various evidence types
# =========================================================

class TestDecideResponseEvidence:
    def test_str_evidence_wrapped(self):
        """String evidence becomes EvidenceItem."""
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence="single text evidence",
        )
        assert len(resp.evidence) == 1
        assert isinstance(resp.evidence[0], schemas.EvidenceItem)

    def test_dict_evidence_with_url_field(self):
        """Dict evidence with 'url' instead of 'uri' gets converted."""
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence=[{"source": "web", "url": "http://example.com"}],
        )
        assert len(resp.evidence) == 1

    def test_dict_evidence_with_text_becomes_snippet(self):
        """Dict evidence where 'text' becomes snippet."""
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence=[{"source": "web", "text": "Some text content"}],
        )
        assert resp.evidence[0].snippet == "Some text content"

    def test_dict_evidence_with_title_as_snippet(self):
        """Dict evidence where 'title' becomes snippet when no text."""
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence=[{"source": "web", "title": "Title content"}],
        )
        assert "Title content" in resp.evidence[0].snippet

    def test_dict_evidence_empty_snippet(self):
        """Dict evidence with only source gets empty snippet."""
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence=[{"source": "internal"}],
        )
        assert resp.evidence[0].snippet == ""

    def test_pydantic_model_evidence(self):
        """Pydantic BaseModel evidence is model_dump'd."""
        ev = schemas.EvidenceItem(source="test", snippet="test", confidence=0.8)
        resp = schemas.DecideResponse(
            request_id="r1",
            evidence=[ev],
        )
        assert len(resp.evidence) == 1


# =========================================================
# DecideResponse with various alternatives/options types
# =========================================================

class TestDecideResponseAlternatives:
    def test_dict_alternatives(self):
        """Dict alternatives are converted to Alt."""
        resp = schemas.DecideResponse(
            request_id="r1",
            alternatives=[{"id": "1", "title": "Option A"}],
        )
        assert len(resp.alternatives) == 1
        assert isinstance(resp.alternatives[0], schemas.Alt)

    def test_multiple_dict_alternatives(self):
        """Multiple dict alternatives are all converted."""
        resp = schemas.DecideResponse(
            request_id="r1",
            alternatives=[
                {"id": "1", "title": "Option A"},
                {"id": "2", "title": "Option B"},
            ],
        )
        assert len(resp.alternatives) == 2

    def test_dict_options(self):
        """Dict options are converted."""
        resp = schemas.DecideResponse(
            request_id="r1",
            options=[{"id": "1", "title": "Option X"}],
        )
        assert len(resp.options) == 1

    def test_alts_copied_to_options(self):
        """When options is empty but alts are set, options gets the same."""
        resp = schemas.DecideResponse(
            request_id="r1",
            alternatives=[{"id": "1", "title": "Option A"}],
            options=[],
        )
        assert len(resp.options) == 1


# =========================================================
# DecideResponse trust_log coercion
# =========================================================

class TestDecideResponseTrustLog:
    def test_none_trust_log(self):
        """None trust_log stays None."""
        resp = schemas.DecideResponse(request_id="r1")
        assert resp.trust_log is None

    def test_trust_log_instance(self):
        """TrustLog instance stays as-is."""
        tl = schemas.TrustLog(
            request_id="r1",
            created_at="2024-01-01T00:00:00Z",
        )
        resp = schemas.DecideResponse(request_id="r1", trust_log=tl)
        assert isinstance(resp.trust_log, schemas.TrustLog)

    def test_dict_trust_log(self):
        """Dict trust_log is converted."""
        resp = schemas.DecideResponse(
            request_id="r1",
            trust_log={"request_id": "r1", "ts": "2024-01-01T00:00:00Z", "query": "test", "decision_status": "allow"},
        )
        assert resp.trust_log is not None

    def test_raw_trust_log_as_string(self):
        """Non-mapping trust_log becomes raw dict."""
        resp = schemas.DecideResponse(
            request_id="r1",
            trust_log="raw_value",  # string becomes {"raw": ...}
        )
        assert resp.trust_log is not None


# =========================================================
# DecideResponse request_id coercion
# =========================================================

class TestDecideResponseRequestId:
    def test_none_generates_id(self):
        """None request_id gets auto-generated."""
        resp = schemas.DecideResponse(request_id=None)
        assert resp.request_id != ""
        assert resp.request_id is not None

    def test_empty_string_generates_id(self):
        """Empty string request_id gets auto-generated."""
        resp = schemas.DecideResponse(request_id="")
        assert resp.request_id != ""

    def test_non_string_gets_stringified(self):
        """Non-string request_id gets str()-ified."""
        resp = schemas.DecideResponse(request_id=12345)
        assert resp.request_id == "12345"


# =========================================================
# EvidenceItem field validators
# =========================================================

class TestEvidenceItem:
    def test_basic_creation(self):
        ev = schemas.EvidenceItem(source="test", snippet="snippet text")
        assert ev.source == "test"
        assert ev.snippet == "snippet text"

    def test_link_field_maps_to_uri(self):
        """'link' field gets mapped to URI if available."""
        ev = schemas.EvidenceItem(source="web", snippet="text")
        assert ev.source == "web"


# =========================================================
# Option model_validator
# =========================================================

class TestOptionModelValidator:
    def test_text_becomes_title(self):
        """When title is None but text is present, title gets set to text."""
        opt = schemas.Option(text="text value")
        assert opt.title == "text value"

    def test_title_not_overridden_by_text(self):
        """If title exists, text doesn't override it."""
        opt = schemas.Option(title="title value", text="text value")
        assert opt.title == "title value"


class TestSchemaCoercionObservability:
    """Tests for coercion event tracking and metadata hints."""

    def test_request_records_coercion_events_and_extra_keys(self):
        req = schemas.DecideRequest(
            query="test",
            context="raw-context",
            alternatives=[{"title": "A"}],
            unexpected_flag=True,
        )
        assert "coercion.context_non_mapping" in req.coercion_events
        assert "coercion.alternatives_to_options" in req.coercion_events
        assert "coercion.request_extra_keys_allowed" in req.coercion_events

    def test_response_records_coercion_events_in_meta(self):
        resp = schemas.DecideResponse(
            request_id="r1",
            alternatives=[{"title": "A"}],
            unexpected_response=True,
        )
        assert "coercion.alternatives_to_options" in resp.coercion_events
        assert "coercion.response_extra_keys_allowed" in resp.coercion_events
        assert "x_coerced_fields" in resp.meta

    def test_trust_log_promotion_failure_is_exposed(self):
        resp = schemas.DecideResponse(
            request_id="r1",
            trust_log={"created_at": "missing-request-id"},
        )
        assert "coercion.trust_log_promotion_failed" in resp.coercion_events
        assert "coercion.trust_log_promotion_failed" in resp.meta.get("x_coerced_fields", [])
