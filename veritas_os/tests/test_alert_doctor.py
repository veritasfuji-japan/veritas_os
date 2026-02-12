"""Tests for veritas_os/scripts/alert_doctor.py."""

from veritas_os.scripts import alert_doctor


def test_validate_webhook_url_accepts_valid_slack_hosts():
    """Valid Slack webhook domains with HTTPS should be accepted."""
    assert alert_doctor._validate_webhook_url("https://hooks.slack.com/services/a/b/c")
    assert alert_doctor._validate_webhook_url(
        "https://hooks.slack-gov.com/services/a/b/c"
    )


def test_validate_webhook_url_rejects_insecure_or_untrusted_hosts():
    """Non-HTTPS or non-Slack hosts should be rejected."""
    assert not alert_doctor._validate_webhook_url("http://hooks.slack.com/services/a/b/c")
    assert not alert_doctor._validate_webhook_url("https://example.com/services/a/b/c")
    assert not alert_doctor._validate_webhook_url("")


def test_post_slack_rejects_invalid_webhook_without_network(monkeypatch):
    """post_slack should fail fast when webhook URL is invalid."""
    monkeypatch.setattr(alert_doctor, "WEBHOOK", "http://hooks.slack.com/services/a/b/c")

    def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("Network call must not happen for invalid webhook")

    monkeypatch.setattr(alert_doctor.urllib.request, "urlopen", _unexpected_call)
    assert alert_doctor.post_slack("hello") is False


def test_post_slack_succeeds_with_valid_webhook(monkeypatch):
    """post_slack should return True when Slack returns HTTP 200."""
    monkeypatch.setattr(
        alert_doctor,
        "WEBHOOK",
        "https://hooks.slack.com/services/a/b/c",
    )

    class _DummyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _urlopen(*_args, **_kwargs):
        return _DummyResponse()

    monkeypatch.setattr(alert_doctor.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(alert_doctor.time, "sleep", lambda *_args, **_kwargs: None)

    assert alert_doctor.post_slack("hello", max_retry=1) is True
