from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "health_check.py"


spec = importlib.util.spec_from_file_location("health_check", MODULE_PATH)
health_check = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(health_check)


def test_is_valid_ipv4_accepts_valid_octets() -> None:
    assert health_check._is_valid_ipv4("127.0.0.1") is True
    assert health_check._is_valid_ipv4("255.255.255.255") is True


def test_is_valid_ipv4_rejects_out_of_range_octets() -> None:
    assert health_check._is_valid_ipv4("256.0.0.1") is False
    assert health_check._is_valid_ipv4("999.1.1.1") is False


def test_validate_url_rejects_credentials_query_and_fragment() -> None:
    assert health_check._validate_url("http://user:pass@example.com") is None
    assert health_check._validate_url("http://example.com/?debug=true") is None
    assert health_check._validate_url("http://example.com/#fragment") is None


def test_validate_url_rejects_invalid_ip_and_port() -> None:
    assert health_check._validate_url("http://999.1.1.1:8000") is None
    assert health_check._validate_url("http://127.0.0.1:70000") is None


def test_validate_url_accepts_safe_http_url() -> None:
    safe_url = "https://127.0.0.1:8000/health"
    assert health_check._validate_url(safe_url) == safe_url


def test_validate_url_rejects_public_host_by_default() -> None:
    assert health_check._validate_url("https://example.com/health") is None


def test_validate_url_accepts_public_host_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("VERITAS_HEALTH_ALLOW_PUBLIC", "1")
    assert (
        health_check._validate_url("https://example.com/health")
        == "https://example.com/health"
    )


def test_validate_url_rejects_hostname_label_starting_with_hyphen() -> None:
    assert health_check._validate_url("https://-bad.example.com/health") is None


def test_validate_url_rejects_hostname_label_ending_with_hyphen() -> None:
    assert health_check._validate_url("https://bad-.example.com/health") is None


def test_validate_url_rejects_hostname_label_too_long() -> None:
    long_label = "a" * 64
    url = f"https://{long_label}.example.com/health"
    assert health_check._validate_url(url) is None


def test_validate_url_rejects_whitespace_and_control_chars() -> None:
    assert health_check._validate_url(" https://127.0.0.1:8000/health") is None
    assert health_check._validate_url("https://127.0.0.1:8000/hea\nlth") is None


def test_validate_url_rejects_percent_encoded_control_chars() -> None:
    assert health_check._validate_url("https://127.0.0.1:8000/health%0a") is None
    assert health_check._validate_url("https://127.0.0.1:8000/health%0D") is None


def test_check_server_disables_redirect_following(monkeypatch) -> None:
    class DummyResponse:
        ok = True
        status_code = 200
        text = '{"ok": true}'

    called: dict[str, object] = {}

    def fake_get(url: str, timeout: int, allow_redirects: bool):
        called["url"] = url
        called["timeout"] = timeout
        called["allow_redirects"] = allow_redirects
        return DummyResponse()

    monkeypatch.setattr(health_check, "HAS_REQUESTS", True)
    monkeypatch.setattr(health_check.requests, "get", fake_get)

    result = health_check.check_server()

    assert result["ok"] is True
    assert called["timeout"] == 3
    assert called["allow_redirects"] is False


def test_paths_are_scoped_to_repo_scripts_directory() -> None:
    assert health_check.SCRIPTS_BASE == health_check.HERE
    assert health_check.LOGS_DIR == health_check.HERE / "logs"
    assert health_check.BACKUPS_DIR == health_check.HERE / "backups"
