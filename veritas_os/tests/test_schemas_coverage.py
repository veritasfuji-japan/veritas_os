# veritas_os/tests/test_schemas_coverage.py
"""
Coverage-boost tests for veritas_os/api/schemas.py.
Focus on validators, coercion functions, and edge cases.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, List

import pytest

from veritas_os.api.schemas import (
    _as_list,
    _coerce_context,
    Alt,
    AltItem,
    Context,
    DecideRequest,
    DecideResponse,
    EvidenceItem,
    FujiDecision,
    Gate,
    Option,
    TrustLog,
    ValuesOut,
    _altin_to_altitem,
    _is_mapping,
)


# =========================================================
# 1. _as_list edge cases
# =========================================================


class TestAsListExtended:
    def test_none(self):
        assert _as_list(None) == []

    def test_list_passthrough(self):
        assert _as_list([1, 2]) == [1, 2]

    def test_dict_wraps(self):
        assert _as_list({"a": 1}) == [{"a": 1}]

    def test_ordered_dict(self):
        od = OrderedDict([("x", 1)])
        result = _as_list(od)
        assert len(result) == 1
        assert result[0] == {"x": 1}

    def test_string_wraps(self):
        assert _as_list("hello") == ["hello"]

    def test_int_wraps(self):
        assert _as_list(42) == [42]

    def test_float_wraps(self):
        assert _as_list(3.14) == [3.14]

    def test_bool_wraps(self):
        assert _as_list(True) == [True]

    def test_tuple_converts(self):
        assert _as_list((1, 2, 3)) == [1, 2, 3]

    def test_set_converts(self):
        result = _as_list({1, 2})
        assert sorted(result) == [1, 2]

    def test_generator_converts(self):
        gen = (x * 2 for x in [1, 2, 3])
        assert _as_list(gen) == [2, 4, 6]

    def test_non_iterable_wraps(self):
        class Opaque:
            pass
        obj = Opaque()
        result = _as_list(obj)
        assert result == [obj]


# =========================================================
# 2. _coerce_context
# =========================================================


class TestCoerceContext:
    def test_none_returns_empty(self):
        assert _coerce_context(None) == {}

    def test_dict_passthrough(self):
        d = {"user_id": "u1", "query": "q"}
        assert _coerce_context(d) == d

    def test_context_object(self):
        ctx = Context(user_id="u1", query="q")
        result = _coerce_context(ctx)
        assert isinstance(result, dict)
        assert result["user_id"] == "u1"

    def test_mapping_like(self):
        od = OrderedDict([("a", 1)])
        result = _coerce_context(od)
        assert result == {"a": 1}

    def test_scalar_wraps_as_raw(self):
        result = _coerce_context(42)
        assert result == {"raw": 42}

    def test_string_wraps_as_raw(self):
        result = _coerce_context("some string")
        assert result == {"raw": "some string"}


# =========================================================
# 3. EvidenceItem validator
# =========================================================


class TestEvidenceItemValidator:
    def test_default_source(self):
        ev = EvidenceItem()
        assert ev.source == "unknown"

    def test_empty_source_coerced(self):
        ev = EvidenceItem(source="")
        assert ev.source == "unknown"

    def test_uri_from_url_extra(self):
        ev = EvidenceItem.model_validate({"url": "http://example.com", "snippet": "s"})
        assert ev.uri == "http://example.com"

    def test_uri_from_link_extra(self):
        ev = EvidenceItem.model_validate({"link": "http://link.com", "snippet": "s"})
        assert ev.uri == "http://link.com"

    def test_snippet_fallback_to_title(self):
        ev = EvidenceItem(title="My Title", snippet="")
        assert ev.snippet == "My Title"

    def test_snippet_fallback_to_uri(self):
        ev = EvidenceItem(uri="http://example.com", snippet="", title=None)
        assert ev.snippet == "http://example.com"

    def test_confidence_clamped(self):
        ev = EvidenceItem(confidence=2.0)
        assert ev.confidence == 1.0

    def test_confidence_negative_clamped(self):
        ev = EvidenceItem(confidence=-0.5)
        assert ev.confidence == 0.0

    def test_confidence_default_value(self):
        ev = EvidenceItem()
        assert ev.confidence == 0.7


# =========================================================
# 4. DecideRequest validators
# =========================================================


class TestDecideRequestValidators:
    def test_context_from_none(self):
        req = DecideRequest(query="test", context=None)
        assert req.context == {}

    def test_context_from_dict(self):
        req = DecideRequest(query="q", context={"user_id": "u1", "query": "q"})
        assert req.context["user_id"] == "u1"

    def test_alternatives_from_none(self):
        req = DecideRequest(query="q")
        assert req.alternatives is not None

    def test_alternatives_from_dict(self):
        req = DecideRequest(query="q", alternatives={"title": "opt1"})
        assert len(req.alternatives) == 1
        assert req.alternatives[0].title == "opt1"

    def test_options_mirror_to_alternatives(self):
        req = DecideRequest(query="q", options=[{"title": "A"}])
        assert len(req.alternatives) >= 1

    def test_alternatives_priority_over_options(self):
        req = DecideRequest(
            query="q",
            alternatives=[{"title": "A"}],
            options=[{"title": "B"}],
        )
        assert req.alternatives[0].title == "A"

    def test_scalar_alternative(self):
        req = DecideRequest(query="q", alternatives=["option_text"])
        assert req.alternatives[0].title == "option_text"


# =========================================================
# 5. DecideResponse validators
# =========================================================


class TestDecideResponseValidators:
    def test_request_id_generated_when_none(self):
        resp = DecideResponse(request_id=None)
        assert len(resp.request_id) > 0

    def test_evidence_from_string(self):
        resp = DecideResponse(evidence="some text evidence")
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "text"
        assert resp.evidence[0].snippet == "some text evidence"

    def test_evidence_from_dict(self):
        resp = DecideResponse(evidence={"source": "web", "snippet": "info"})
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "web"

    def test_evidence_from_list_of_strings(self):
        resp = DecideResponse(evidence=["ev1", "ev2"])
        assert len(resp.evidence) == 2
        assert all(e.source == "text" for e in resp.evidence)

    def test_evidence_dict_url_to_uri(self):
        resp = DecideResponse(evidence=[{"url": "http://a.com", "snippet": "s"}])
        assert resp.evidence[0].uri == "http://a.com"

    def test_evidence_dict_snippet_from_text(self):
        resp = DecideResponse(evidence=[{"text": "my text"}])
        assert resp.evidence[0].snippet == "my text"

    def test_alternatives_mirror_to_options(self):
        resp = DecideResponse(alternatives=[{"title": "A"}])
        assert len(resp.options) > 0

    def test_options_mirror_to_alternatives(self):
        resp = DecideResponse(options=[{"title": "B"}])
        assert len(resp.alternatives) > 0

    def test_critique_from_string(self):
        resp = DecideResponse(critique="issue found")
        assert resp.critique == ["issue found"]

    def test_debate_from_dict(self):
        resp = DecideResponse(debate={"stance": "for", "argument": "good"})
        assert len(resp.debate) == 1

    def test_trust_log_from_dict(self):
        tl_data = {
            "request_id": "r1",
            "created_at": "2024-01-01T00:00:00Z",
            "sources": [],
            "critics": [],
            "checks": [],
        }
        resp = DecideResponse(trust_log=tl_data)
        assert isinstance(resp.trust_log, TrustLog)

    def test_trust_log_from_invalid_type(self):
        resp = DecideResponse(trust_log=12345)
        assert resp.trust_log is not None

    def test_evidence_unknown_type(self):
        resp = DecideResponse(evidence=[42])
        assert len(resp.evidence) == 1
        assert resp.evidence[0].source == "unknown"

    def test_alt_from_dict_list(self):
        resp = DecideResponse(alternatives=[{"title": "opt1"}, {"title": "opt2"}])
        assert len(resp.alternatives) == 2
        assert resp.alternatives[0].title == "opt1"


# =========================================================
# 6. Alt model
# =========================================================


class TestAltModel:
    def test_auto_id(self):
        alt = Alt()
        assert len(alt.id) > 0

    def test_auto_title(self):
        alt = Alt(id="", title="")
        assert alt.title.startswith("option-")

    def test_explicit_values(self):
        alt = Alt(id="a1", title="My Option", score=0.9)
        assert alt.id == "a1"
        assert alt.title == "My Option"


# =========================================================
# 7. Option model
# =========================================================


class TestOptionModel:
    def test_text_to_title(self):
        opt = Option(text="from text")
        assert opt.title == "from text"

    def test_title_preserved(self):
        opt = Option(title="explicit", text="fallback")
        assert opt.title == "explicit"


# =========================================================
# 8. _altin_to_altitem
# =========================================================


class TestAltinToAltitem:
    def test_none(self):
        result = _altin_to_altitem(None)
        assert isinstance(result, AltItem)

    def test_altitem_passthrough(self):
        ai = AltItem(title="test")
        assert _altin_to_altitem(ai) is ai

    def test_option_converts(self):
        opt = Option(title="opt")
        result = _altin_to_altitem(opt)
        assert isinstance(result, AltItem)
        assert result.title == "opt"

    def test_dict_converts(self):
        result = _altin_to_altitem({"title": "dict opt"})
        assert result.title == "dict opt"

    def test_scalar_converts(self):
        result = _altin_to_altitem(42)
        assert result.title == "42"


# =========================================================
# 9. _is_mapping
# =========================================================


class TestIsMapping:
    def test_dict(self):
        assert _is_mapping({}) is True

    def test_ordered_dict(self):
        assert _is_mapping(OrderedDict()) is True

    def test_list(self):
        assert _is_mapping([]) is False

    def test_string(self):
        assert _is_mapping("hello") is False
