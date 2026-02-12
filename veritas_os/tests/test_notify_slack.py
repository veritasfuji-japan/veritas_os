"""Tests for scripts/notify_slack.py security-sensitive behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notify_slack.py"


def load_module():
    """Load notify_slack.py as an importable module for tests."""
    fake_requests = types.SimpleNamespace(
        post=lambda **_: None,
        RequestException=Exception,
    )
    sys.modules.setdefault("requests", fake_requests)

    spec = importlib.util.spec_from_file_location("notify_slack", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _DummyResponse:
    """Test double for requests.Response-like behavior."""

    def __init__(self, status_code: int):
        self.status_code = status_code


class NotifySlackTests(unittest.TestCase):
    """Behavioral tests for Slack notification script hardening."""

    def test_send_slack_uses_timeout(self):
        """requests.post should always include a finite timeout value."""
        module = load_module()
        observed = {}

        def fake_post(url, json, timeout):
            observed["url"] = url
            observed["json"] = json
            observed["timeout"] = timeout
            return _DummyResponse(200)

        with mock.patch.object(module.requests, "post", side_effect=fake_post):
            exit_code = module.send_slack_notification(
                "https://hooks.slack.com/services/a/b/c",
                "hello",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(observed["url"], "https://hooks.slack.com/services/a/b/c")
        self.assertEqual(observed["timeout"], module.DEFAULT_TIMEOUT_SEC)
        self.assertIn("hello", observed["json"]["text"])

    def test_send_slack_error_log_does_not_include_response_text(self):
        """Error logging must avoid printing server response body."""
        module = load_module()

        with mock.patch.object(module.requests, "post", return_value=_DummyResponse(500)):
            with mock.patch("builtins.print") as mock_print:
                exit_code = module.send_slack_notification(
                    "https://hooks.slack.com/services/a/b/c",
                    "hello",
                )

        self.assertEqual(exit_code, 1)
        logged = "\n".join(" ".join(map(str, call.args)) for call in mock_print.call_args_list)
        self.assertIn("status_code=500", logged)
        self.assertNotIn("response", logged.lower())

    def test_main_returns_error_when_webhook_env_missing(self):
        """CLI should fail with non-zero status when webhook URL is absent."""
        module = load_module()

        with mock.patch.object(module.os, "getenv", return_value=None):
            with mock.patch.object(module.sys, "argv", ["notify_slack.py", "hi"]):
                exit_code = module.main()

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
