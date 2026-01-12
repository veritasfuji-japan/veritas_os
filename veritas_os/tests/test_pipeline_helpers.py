# -*- coding: utf-8 -*-
"""
Helper coverage tests for veritas_os.core.pipeline

Targets:
- _to_dict: cover __dict__ success + exception fallback
- _get_request_params: cover request.params path + exception swallow
"""

from veritas_os.core.pipeline import _to_dict, _get_request_params


def test__to_dict_uses___dict__():
    class Foo:
        def __init__(self):
            self.a = 1
            self.b = "x"

    assert _to_dict(Foo()) == {"a": 1, "b": "x"}


def test__to_dict___dict___conversion_error_returns_empty():
    class Weird:
        # hasattr(o, "__dict__") is True, but dict(o.__dict__) should fail
        def __getattribute__(self, name):
            if name == "__dict__":
                return 123  # dict(123) -> TypeError
            return object.__getattribute__(self, name)

    assert _to_dict(Weird()) == {}


def test__get_request_params_reads_params():
    class Req:
        query_params = None
        params = {"p": "1", "q": "2"}

    out = _get_request_params(Req())
    assert out == {"p": "1", "q": "2"}


def test__get_request_params_params_getattr_error_is_swallowed():
    class BadReq:
        query_params = None

        def __getattribute__(self, name):
            if name == "params":
                raise RuntimeError("boom")
            return object.__getattribute__(self, name)

    out = _get_request_params(BadReq())
    assert out == {}
