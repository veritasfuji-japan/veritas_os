"""SSRF / DNS rebinding protection for Web Search adapter.

This module centralizes all host-validation, private-IP detection,
and DNS rebinding guard logic used by ``veritas_os.tools.web_search``.

Extracted from ``web_search.py`` to isolate security-critical code
for easier review and independent testing.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from functools import lru_cache
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hostname helpers
# ---------------------------------------------------------------------------

def _extract_hostname(url: str) -> str:
    """URLからホスト名を抽出する（スキームなしURLも対応）。"""
    if not url:
        return ""
    candidate = url.strip()
    parsed = urlparse(candidate)
    host = parsed.hostname
    if not host and "://" not in candidate:
        parsed = urlparse(f"http://{candidate}")
        host = parsed.hostname
    return (host or "").lower().rstrip(".")


def _canonicalize_hostname(hostname: str) -> str:
    """Normalize hostnames for policy checks and allowlist matching.

    DNS hostnames may be represented with a trailing dot (absolute form),
    such as ``example.com.``. Treating these as distinct strings can bypass
    exact-match checks and create inconsistent SSRF protections.

    Args:
        hostname: Raw hostname string.

    Returns:
        Canonicalized lowercase hostname without surrounding whitespace
        or a trailing dot.
    """
    return (hostname or "").strip().lower().rstrip(".")


def _is_hostname_exact_or_subdomain(hostname: str, domain: str) -> bool:
    """Return True when hostname is the same domain or a child subdomain.

    This helper prevents suffix-matching mistakes such as treating
    ``evilveritas.com`` as ``veritas.com``. Only exact matches or dot-bounded
    subdomains (e.g., ``www.veritas.com``) are accepted.
    """
    normalized_host = _canonicalize_hostname(hostname)
    normalized_domain = _canonicalize_hostname(domain)
    if not normalized_host or not normalized_domain:
        return False
    return (
        normalized_host == normalized_domain
        or normalized_host.endswith(f".{normalized_domain}")
    )


# ---------------------------------------------------------------------------
# Private / local host detection
# ---------------------------------------------------------------------------

def _is_obviously_private_or_local_host(hostname: str) -> bool:
    """文字列情報だけで private/local と判断できるホストを検出する。"""
    host = _canonicalize_hostname(hostname)
    if not host:
        return True

    if host in {"localhost", "localhost.localdomain"}:
        return True

    # Single-label host names and local/internal pseudo-TLDs are typically
    # internal-only and should not be used for outbound web search endpoints.
    if "." not in host:
        return True

    if host.endswith((".local", ".internal", ".localhost", ".localdomain")):
        return True

    try:
        ip = ipaddress.ip_address(host)
        return not ip.is_global
    except ValueError:
        pass

    return False


@lru_cache(maxsize=256)
def _resolve_host_infos(host: str) -> tuple[tuple[Any, ...], ...]:
    """Resolve host addresses with LRU caching for successful lookups only.

    The function intentionally propagates resolution errors so failed lookups
    are not cached. This avoids long-lived false positives when DNS fails
    transiently in CI/sandbox environments.
    """
    return tuple(socket.getaddrinfo(host, None))


def _is_private_or_local_host(hostname: str) -> bool:
    """ホストが localhost / private / loopback / link-local かを判定する。

    DNS 解決の成功結果だけを LRU キャッシュし、失敗はキャッシュしない。
    これにより一時的な名前解決障害での過剰ブロックを緩和する。
    """
    host = _canonicalize_hostname(hostname)
    if _is_obviously_private_or_local_host(host):
        return True

    try:
        infos = _resolve_host_infos(host)
    except (socket.gaierror, OSError, UnicodeError):
        # DNS解決不能や不正なホスト名（IDNA変換エラー等）は
        # 誤設定かローカル向け名の可能性が高いため、保守的にブロックする。
        return True

    for info in infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if not ip.is_global:
            return True
    return False


# ---------------------------------------------------------------------------
# DNS rebinding guard
# ---------------------------------------------------------------------------

def _resolve_public_ips_uncached(hostname: str) -> set[str]:
    """Resolve hostname without cache and require globally routable IPs.

    This request-time lookup narrows DNS rebinding / TOCTOU windows between
    endpoint validation and the outbound web-search request.

    Args:
        hostname: Endpoint hostname to resolve.

    Returns:
        Set of resolved global IP literals.

    Raises:
        ValueError: Hostname is empty, invalid, unresolvable, or non-global.
    """
    host = _canonicalize_hostname(hostname)
    if _is_obviously_private_or_local_host(host):
        raise ValueError("host is private or local")

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        raise ValueError("host is not resolvable") from exc

    resolved_ips: set[str] = set()
    for info in infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError as exc:
            raise ValueError("host resolved to invalid IP") from exc
        if not ip.is_global:
            raise ValueError("host resolved to non-global IP")
        resolved_ips.add(str(ip))

    if not resolved_ips:
        raise ValueError("host resolved to no valid IPs")

    return resolved_ips


def _extract_public_ips_for_url(url: str) -> set[str]:
    """Extract URL host and resolve it to global IPs without cache."""
    parsed = urlparse((url or "").strip())
    host = _canonicalize_hostname(parsed.hostname or "")
    if not host:
        raise ValueError("url has no hostname")
    return _resolve_public_ips_uncached(host)


def _validate_rebinding_guard(url: str, expected_ips: set[str]) -> None:
    """Ensure request-time DNS answers match preflight-resolved IPs."""
    current_ips = _extract_public_ips_for_url(url)
    if current_ips != expected_ips:
        raise ValueError("websearch endpoint DNS result changed during request")


def _clear_private_host_cache() -> None:
    """Clear DNS lookup cache used by SSRF host checks."""
    _resolve_host_infos.cache_clear()


# Attach cache_clear for monkeypatch compatibility
_is_private_or_local_host.cache_clear = _clear_private_host_cache  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

def _sanitize_websearch_url(url: str) -> str:
    """Validate env-derived web search URL and enforce HTTPS-only endpoints.

    Security note:
        Runtime env overrides are useful for incident response, but they must
        still respect scheme restrictions to avoid accidental use of
        non-network schemes (e.g. ``file://``).
    """
    candidate = (url or "").strip()
    if not candidate:
        return ""

    parsed = urlparse(candidate)
    if parsed.scheme != "https":
        logging.getLogger(__name__).warning(
            "VERITAS_WEBSEARCH_URL must use https (got scheme=%r); URL will be ignored",
            parsed.scheme,
        )
        return ""

    # URL 埋め込み資格情報は漏えい・誤設定の原因になり得るため禁止。
    if parsed.username or parsed.password:
        logging.getLogger(__name__).warning(
            "VERITAS_WEBSEARCH_URL must not include embedded credentials; URL will be ignored"
        )
        return ""

    # 明示的なホスト名がないURLは requests 側で曖昧解釈される恐れがあるため拒否。
    if not parsed.hostname:
        logging.getLogger(__name__).warning(
            "VERITAS_WEBSEARCH_URL must include a hostname; URL will be ignored"
        )
        return ""

    return candidate


def _is_allowed_websearch_url(
    url: str,
    *,
    resolve_allowlist_fn=None,
) -> bool:
    """WEBSEARCH endpoint のスキーム・ホスト安全性を検証する。

    Security note:
        API key を平文送信しないため、HTTPS のみ許可する。

    Args:
        url: Target URL to validate.
        resolve_allowlist_fn: Callable returning current host allowlist set.
            If None, an empty set is used (no allowlist restriction).
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        return False

    # URL 埋め込み資格情報の利用を禁止し、誤設定や漏えいリスクを低減する。
    if parsed.username or parsed.password:
        return False

    host = _canonicalize_hostname(parsed.hostname or "")
    if resolve_allowlist_fn is not None:
        host_allowlist = resolve_allowlist_fn()
    else:
        host_allowlist: set[str] = set()

    if host_allowlist:
        if host not in host_allowlist:
            return False
        # Allowlisted hosts must also resolve to public IPs.
        # This prevents DNS rebinding/misconfiguration from tunneling
        # requests into private networks.
        return not _is_private_or_local_host(host)

    if _is_private_or_local_host(host):
        return False

    return True
