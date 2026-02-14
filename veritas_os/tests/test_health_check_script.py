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
