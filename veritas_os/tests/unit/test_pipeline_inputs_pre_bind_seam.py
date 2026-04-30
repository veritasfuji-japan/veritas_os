# -*- coding: utf-8 -*-
"""Tests for canonical pre-bind deterministic seam in pipeline input normalization."""

from __future__ import annotations

from veritas_os.core.pipeline_inputs import normalize_pipeline_inputs


class _DummyReq:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _DummyRequest:
    query_params = {}
    params = {}


def test_pre_bind_signal_is_normalized_from_context_input_seam():
    payload = {
        "query": "canonical seam test",
        "context": {
            "user_id": "u",
            "pre_bind_participation_signal": {
                "interpretation_space_narrowing": "open",
                "counterfactual_availability": "high",
                "intervention_headroom": "high",
                "structural_openness": "open",
            },
        },
    }
    ctx = normalize_pipeline_inputs(_DummyReq(payload), _DummyRequest())
    signal = ctx.response_extras["participation_signal"]
    assert signal["signal_family"] == "participation_signal"
    assert signal["interpretation_space_narrowing"] == "open"


def test_pre_bind_signal_hook_is_isolated_from_runtime_context():
    payload = {
        "query": "canonical seam isolation test",
        "context": {
            "user_id": "u",
            "pre_bind_participation_signal": {
                "interpretation_space_narrowing": "closed",
                "counterfactual_availability": "none",
                "intervention_headroom": "low",
                "structural_openness": "closed",
            },
        },
    }
    ctx = normalize_pipeline_inputs(_DummyReq(payload), _DummyRequest())
    assert "pre_bind_participation_signal" not in ctx.context
