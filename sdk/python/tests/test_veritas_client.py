"""Unit tests for the dependency-free VERITAS reference client."""

import io
import json
import unittest
from unittest import mock
from urllib import error

from veritas_client import (
    VeritasAPIError,
    VeritasClient,
    VeritasTransportError,
)


class _Response:
    """Minimal context-managed urllib response test double."""

    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class VeritasClientTests(unittest.TestCase):
    """Verify request construction and explicit failure behavior."""

    def setUp(self) -> None:
        """Create a client used by each test."""
        self.client = VeritasClient("https://veritas.example/", "test-key", 5)

    @mock.patch("veritas_client.request.urlopen")
    def test_decide_posts_authenticated_json(self, urlopen: mock.Mock) -> None:
        """The decision helper posts JSON to the existing endpoint."""
        urlopen.return_value = _Response({"status": "candidate"})

        result = self.client.decide({"query": "review this"})

        self.assertEqual(result, {"status": "candidate"})
        sent_request = urlopen.call_args.args[0]
        self.assertEqual(sent_request.full_url, "https://veritas.example/v1/decide")
        self.assertEqual(sent_request.get_header("X-api-key"), "test-key")
        self.assertEqual(json.loads(sent_request.data), {"query": "review this"})
        urlopen.assert_called_once_with(sent_request, timeout=5)

    @mock.patch("veritas_client.request.urlopen")
    def test_non_2xx_response_raises_api_error(self, urlopen: mock.Mock) -> None:
        """HTTP failures preserve the status and response body."""
        urlopen.side_effect = error.HTTPError(
            self.client.base_url,
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"detail":"denied"}'),
        )

        with self.assertRaises(VeritasAPIError) as raised:
            self.client.decide({"query": "review this"})

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.response_body, '{"detail":"denied"}')

    @mock.patch("veritas_client.request.urlopen")
    def test_non_object_response_raises_transport_error(
        self,
        urlopen: mock.Mock,
    ) -> None:
        """A JSON response must match the SDK's object return contract."""
        urlopen.return_value = _Response(["unexpected"])

        with self.assertRaises(VeritasTransportError):
            self.client.decide({"query": "review this"})


if __name__ == "__main__":
    unittest.main()
