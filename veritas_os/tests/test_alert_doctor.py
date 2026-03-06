"""Tests for veritas_os/scripts/alert_doctor.py."""

from pathlib import Path

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


def test_validate_webhook_url_rejects_ports_userinfo_and_extra_parts():
    """Webhook URL with unsafe URL parts should be rejected."""
    assert not alert_doctor._validate_webhook_url(
        "https://hooks.slack.com:443/services/a/b/c"
    )
    assert not alert_doctor._validate_webhook_url(
        "https://user@hooks.slack.com/services/a/b/c"
    )
    assert not alert_doctor._validate_webhook_url(
        "https://hooks.slack.com/services/a/b/c?debug=true"
    )
    assert not alert_doctor._validate_webhook_url(
        "https://hooks.slack.com/not-services/a/b/c"
    )




def test_validate_webhook_url_rejects_malformed_port():
    """Webhook URL with malformed port should be rejected safely."""
    assert not alert_doctor._validate_webhook_url(
        "https://hooks.slack.com:abc/services/a/b/c"
    )

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


def test_safe_snippet_truncates_and_flattens_whitespace():
    """_safe_snippet should flatten whitespace and cap long text."""
    source = "line1\nline2\tline3 " + ("x" * 500)
    got = alert_doctor._safe_snippet(source, max_chars=20)

    assert "\n" not in got
    assert "\t" not in got
    assert got.endswith("...")
    assert len(got) == 23


def test_validate_health_url_accepts_only_localhosts():
    """Health URL should allow only loopback destinations."""
    assert alert_doctor._validate_health_url("http://127.0.0.1:8000/health")
    assert alert_doctor._validate_health_url("https://localhost/health")
    assert not alert_doctor._validate_health_url("http://127.0.0.1:8000/")
    assert not alert_doctor._validate_health_url("http://127.0.0.1:8000/metrics")
    assert not alert_doctor._validate_health_url(
        "http://127.0.0.1:8000/health?verbose=1"
    )
    assert not alert_doctor._validate_health_url("http://example.com/health")
    assert not alert_doctor._validate_health_url("http://user@127.0.0.1/health")




def test_validate_health_url_rejects_malformed_port():
    """Health URL with malformed port should be rejected safely."""
    assert not alert_doctor._validate_health_url("http://127.0.0.1:abc/health")

def test_http_get_blocks_non_local_url_without_network(monkeypatch):
    """http_get should reject non-local targets before urlopen is called."""

    def _unexpected_call(*_args, **_kwargs):
        raise AssertionError("Network call must not happen for blocked URL")

    monkeypatch.setattr(alert_doctor.urllib.request, "urlopen", _unexpected_call)

    status, body = alert_doctor.http_get("http://example.com/health")
    assert status is None
    assert body == "health URL blocked by security policy"


def test_run_heal_truncates_failure_output(monkeypatch, tmp_path):
    """run_heal should sanitize and truncate subprocess failure output."""
    heal_script = tmp_path / "heal.sh"
    heal_script.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")

    monkeypatch.setattr(alert_doctor, "HEAL_SCRIPT", Path(heal_script))
    monkeypatch.setattr(
        alert_doctor,
        "_validate_heal_script_path",
        lambda *_args, **_kwargs: True,
    )

    def _raise(*_args, **_kwargs):
        raise alert_doctor.subprocess.CalledProcessError(
            1,
            ["/bin/bash", "heal.sh"],
            output="A" * 1000,
        )

    monkeypatch.setattr(alert_doctor.subprocess, "check_output", _raise)

    ok, info = alert_doctor.run_heal()
    assert ok is False
    assert info.startswith("heal failed: rc=1, out=")
    assert info.endswith("...")


def test_validate_heal_script_path_rejects_group_writable_file(tmp_path):
    """_validate_heal_script_path should reject group/other writable scripts."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    heal_script = scripts_dir / "heal.sh"
    heal_script.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")
    heal_script.chmod(0o775)

    original_scripts_dir = alert_doctor.SCRIPTS_DIR
    alert_doctor.SCRIPTS_DIR = scripts_dir
    try:
        assert not alert_doctor._validate_heal_script_path(heal_script)
    finally:
        alert_doctor.SCRIPTS_DIR = original_scripts_dir


def test_resolve_heal_timeout_seconds_fallbacks(monkeypatch):
    """Invalid timeout env values should fall back to default timeout."""
    monkeypatch.setenv("VERITAS_HEAL_TIMEOUT_SEC", "invalid")
    assert (
        alert_doctor._resolve_heal_timeout_seconds()
        == alert_doctor.DEFAULT_HEAL_TIMEOUT_SEC
    )


def test_resolve_heal_timeout_seconds_caps_large_value(monkeypatch):
    """Large timeout env values should be capped to a safe upper bound."""
    monkeypatch.setenv("VERITAS_HEAL_TIMEOUT_SEC", "9999")
    assert (
        alert_doctor._resolve_heal_timeout_seconds()
        == alert_doctor.MAX_HEAL_TIMEOUT_SEC
    )

    monkeypatch.setenv("VERITAS_HEAL_TIMEOUT_SEC", "0")
    assert (
        alert_doctor._resolve_heal_timeout_seconds()
        == alert_doctor.DEFAULT_HEAL_TIMEOUT_SEC
    )


def test_run_heal_handles_timeout(monkeypatch, tmp_path):
    """run_heal should return a safe timeout message when heal script stalls."""
    heal_script = tmp_path / "heal.sh"
    heal_script.write_text("#!/bin/bash\necho ok\n", encoding="utf-8")

    monkeypatch.setattr(alert_doctor, "HEAL_SCRIPT", Path(heal_script))
    monkeypatch.setattr(
        alert_doctor,
        "_validate_heal_script_path",
        lambda *_args, **_kwargs: True,
    )

    def _raise(*_args, **_kwargs):
        raise alert_doctor.subprocess.TimeoutExpired(
            cmd=["/bin/bash", "heal.sh"],
            timeout=1,
            output=b"partial\noutput",
        )

    monkeypatch.setattr(alert_doctor.subprocess, "check_output", _raise)

    ok, info = alert_doctor.run_heal()
    assert ok is False
    assert info == "heal timeout: partial output"


def test_post_slack_retries_and_returns_false_on_persistent_failure(monkeypatch):
    """post_slack should retry and eventually return False on repeated errors."""
    monkeypatch.setattr(
        alert_doctor,
        "WEBHOOK",
        "https://hooks.slack.com/services/a/b/c",
    )

    calls = {"count": 0}

    def _always_fail(*_args, **_kwargs):
        calls["count"] += 1
        raise alert_doctor.urllib.error.URLError("network down")

    monkeypatch.setattr(alert_doctor.urllib.request, "urlopen", _always_fail)
    monkeypatch.setattr(alert_doctor.time, "sleep", lambda *_args, **_kwargs: None)

    assert alert_doctor.post_slack("hello", max_retry=3) is False
    assert calls["count"] == 3


def test_run_heal_success_after_health_recovery(monkeypatch, tmp_path):
    """run_heal should report success when health endpoint recovers."""
    heal_script = tmp_path / "heal.sh"
    heal_script.write_text("#!/bin/bash\necho healed\n", encoding="utf-8")

    monkeypatch.setattr(alert_doctor, "HEAL_SCRIPT", Path(heal_script))
    monkeypatch.setattr(
        alert_doctor,
        "_validate_heal_script_path",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        alert_doctor.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "healed\n",
    )
    monkeypatch.setattr(alert_doctor.time, "sleep", lambda *_args, **_kwargs: None)

    states = iter([(503, "not ready"), (200, '{"ok": true}')])
    monkeypatch.setattr(alert_doctor, "http_get", lambda *_args, **_kwargs: next(states))

    ok, info = alert_doctor.run_heal()
    assert ok is True
    assert info == "healed"


def test_main_warn_level_posts_summary_only(monkeypatch, tmp_path):
    """main should post one summary notification when level is WARN."""
    report = tmp_path / "doctor_report.json"
    report.write_text(
        '{"total_logs": 10, "avg_uncertainty": 0.41, "last_check": "now", "keywords": {}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(alert_doctor, "REPORT_JSON", report)
    monkeypatch.setattr(alert_doctor, "THRESH", 0.5)
    monkeypatch.setattr(alert_doctor, "HEAL_ON_HIGH", True)

    posted = []
    monkeypatch.setattr(alert_doctor, "post_slack", lambda msg: posted.append(msg) or True)
    monkeypatch.setattr(
        alert_doctor,
        "run_heal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("run_heal not expected")),
    )

    alert_doctor.main()

    assert len(posted) == 1
    assert "[WARN]" in posted[0]


def test_main_high_level_runs_heal_and_health_check(monkeypatch, tmp_path):
    """main should run self-heal and post follow-up messages for HIGH level."""
    report = tmp_path / "doctor_report.json"
    report.write_text(
        '{"total_logs": 20, "avg_uncertainty": 0.8, "last_check": "later", "keywords": {"risk": 2}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(alert_doctor, "REPORT_JSON", report)
    monkeypatch.setattr(alert_doctor, "THRESH", 0.5)
    monkeypatch.setattr(alert_doctor, "HEAL_ON_HIGH", True)
    monkeypatch.setattr(alert_doctor, "HEALTH_URL", "http://127.0.0.1:8000/health")
    monkeypatch.setattr(alert_doctor, "run_heal", lambda: (True, "healed"))
    monkeypatch.setattr(alert_doctor, "http_get", lambda *_args, **_kwargs: (200, "ok"))

    posted = []
    monkeypatch.setattr(alert_doctor, "post_slack", lambda msg: posted.append(msg) or True)

    alert_doctor.main()

    assert len(posted) == 3
    assert "[HIGH]" in posted[0]
    assert "Self-Heal: OK" in posted[1]
    assert "/health: status=200" in posted[2]
