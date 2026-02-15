"""Tests for scripts/bench.py API key handling and request behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bench.py"


def load_module():
    """Load bench.py as a module for unit testing."""
    fake_requests = types.SimpleNamespace(post=lambda **_: None)
    fake_yaml = types.SimpleNamespace(safe_load=lambda _: {})
    sys.modules.setdefault("requests", fake_requests)
    sys.modules.setdefault("yaml", fake_yaml)

    spec = importlib.util.spec_from_file_location("bench_script", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DummyResponse:
    """Simple response test double for requests.post."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class BenchScriptTests(unittest.TestCase):
    """Behavioral tests for bench script."""

    def test_run_bench_requires_api_key(self):
        module = load_module()
        with (
            mock.patch.dict(module.os.environ, {}, clear=True),
            mock.patch.object(module.Path, "exists", return_value=True),
            mock.patch.object(module, "open", mock.mock_open(read_data="id: t\nrequest: {}\n"), create=True),
            mock.patch.object(module.yaml, "safe_load", return_value={"id": "t", "request": {}}),
        ):
            with self.assertRaises(RuntimeError):
                module.run_bench("x.yaml")

    def test_run_bench_uses_env_api_key(self):
        module = load_module()
        request_info = {}

        def fake_post(url, headers, json, timeout):
            request_info["url"] = url
            request_info["headers"] = headers
            request_info["timeout"] = timeout
            return DummyResponse({"chosen": {}, "fuji": {}, "telos_score": 0})

        with (
            mock.patch.dict(module.os.environ, {"VERITAS_API_KEY": "expected-key"}, clear=False),
            mock.patch.object(module.Path, "exists", return_value=True),
            mock.patch.object(module, "open", mock.mock_open(read_data="id: t\nrequest: {}\n"), create=True),
            mock.patch.object(module.yaml, "safe_load", return_value={"id": "t", "name": "n", "request": {}}),
            mock.patch.object(module.requests, "post", side_effect=fake_post),
            mock.patch.object(module.json, "dump"),
        ):
            module.run_bench("x.yaml")

        self.assertEqual(request_info["url"], f"{module.API_BASE}/v1/decide")
        self.assertEqual(request_info["headers"]["X-API-Key"], "expected-key")
        self.assertEqual(request_info["timeout"], 120)


if __name__ == "__main__":
    unittest.main()
