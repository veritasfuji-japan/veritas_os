"""Tests for scripts/decide_plan.py entry points and HTTP call behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "decide_plan.py"


def load_module():
    """Load decide_plan.py as a module for unit testing."""
    fake_requests = types.SimpleNamespace(post=lambda **_: None)
    sys.modules.setdefault("requests", fake_requests)

    spec = importlib.util.spec_from_file_location("decide_plan", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DummyResponse:
    """Simple response test double for requests.post."""

    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.text or "http error")


class DecidePlanScriptTests(unittest.TestCase):
    """Behavioral tests for decide_plan script entry points."""

    def test_main_routes_to_agi_next_step(self):
        module = load_module()
        called = {"value": False}

        def fake_agi_next_step():
            called["value"] = True

        with mock.patch.object(module, "agi_next_step", fake_agi_next_step):
            with mock.patch.object(module.sys, "argv", ["decide_plan.py", "--agi-next-step"]):
                module.main()

        self.assertTrue(called["value"])

    def test_main_decide_request_has_timeout(self):
        module = load_module()
        request_info = {}

        def fake_post(url, headers, data, timeout):
            request_info["url"] = url
            request_info["timeout"] = timeout
            return DummyResponse(
                {
                    "chosen": {"title": "plan"},
                    "extras": {"planner": {"steps": []}},
                }
            )

        with mock.patch.object(module.requests, "post", side_effect=fake_post):
            with mock.patch.object(module.sys, "argv", ["decide_plan.py", "hello"]):
                with self.assertRaises(SystemExit) as exc_info:
                    module.main()

        self.assertEqual(exc_info.exception.code, 0)
        self.assertEqual(request_info["url"], module.API_URL)
        self.assertEqual(request_info["timeout"], module.REQUEST_TIMEOUT)

    def test_agi_next_step_request_has_timeout(self):
        module = load_module()
        request_info = {}

        def fake_post(url, headers, data, timeout):
            request_info["url"] = url
            request_info["timeout"] = timeout
            return DummyResponse(
                {
                    "extras": {
                        "veritas_agi": {"snapshot": {}, "meta": {}, "hint": "h"},
                        "planner": {"steps": [{"title": "t1"}]},
                    }
                }
            )

        with mock.patch.object(module.requests, "post", side_effect=fake_post):
            module.agi_next_step()

        self.assertEqual(request_info["url"], f"{module.BASE_URL}/v1/decide")
        self.assertEqual(request_info["timeout"], module.REQUEST_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
