"""Tests for the import-safe AML/KYC webhook bind SDK example."""

import unittest
from unittest import mock

from examples.aml_kyc_webhook_bind import (
    build_review_payload,
    prepare_bind_payload,
    request_review,
)


class AMLKYCWebhookBindExampleTests(unittest.TestCase):
    """Verify the example stays synthetic and non-executing."""

    def test_build_review_payload_is_synthetic(self) -> None:
        """The review request identifies all case context as synthetic."""
        payload = build_review_payload()

        self.assertEqual(
            payload["context"]["data_classification"],
            "synthetic_example_only",
        )
        self.assertEqual(payload["context"]["case_id"], "synthetic-case-001")

    def test_request_review_only_calls_supplied_client(self) -> None:
        """The optional API step delegates to the supplied SDK client."""
        client = mock.Mock()
        client.decide.return_value = {"decision_id": "synthetic-decision"}

        result = request_review(client)

        client.decide.assert_called_once_with(build_review_payload())
        self.assertEqual(result, {"decision_id": "synthetic-decision"})

    def test_prepare_bind_payload_is_not_executed(self) -> None:
        """The bind data explicitly requires later adjudication."""
        payload = prepare_bind_payload({"decision_id": "synthetic-decision"})

        self.assertEqual(payload["execution_status"], "not_executed")
        self.assertIs(payload["requires_bind_adjudication"], True)
        self.assertEqual(payload["adapter_pattern"], "WebhookBindAdapter")
        self.assertEqual(
            payload["target"],
            "https://example.invalid/aml-kyc-review",
        )


if __name__ == "__main__":
    unittest.main()
