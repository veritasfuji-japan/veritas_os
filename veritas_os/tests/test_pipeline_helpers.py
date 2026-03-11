# -*- coding: utf-8 -*-
"""
Helper coverage tests for veritas_os.core.pipeline

Targets:
- _to_dict: cover model_dump / dict / plain-dict / unknown-object paths
- _get_request_params: cover request.params path + exception swallow
"""

from veritas_os.core.pipeline import _to_dict, _get_request_params


def test__to_dict_with_plain_dict():
    assert _to_dict({"a": 1}) == {"a": 1}


def test__to_dict_with_model_dump():
    class PydanticV2Like:
        def model_dump(self, exclude_none=False):
            return {"x": 10}

    assert _to_dict(PydanticV2Like()) == {"x": 10}


def test__to_dict_with_dict_method():
    class PydanticV1Like:
        def dict(self):
            return {"y": 20}

    assert _to_dict(PydanticV1Like()) == {"y": 20}


def test__to_dict_unknown_object_returns_empty():
    class Foo:
        def __init__(self):
            self.a = 1

    assert _to_dict(Foo()) == {}


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
