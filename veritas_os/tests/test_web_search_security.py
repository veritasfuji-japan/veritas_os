"""Focused security regression tests for web_search_security helpers.

These tests intentionally avoid real network calls by monkeypatching
``socket.getaddrinfo`` and related helpers.
"""

from __future__ import annotations

import socket

import pytest

from veritas_os.tools import web_search_security as sec


class TestHostExtractionAndDomainMatching:
    """Host parsing and exact/subdomain allowlist matching behavior."""

    def test_extract_hostname_supports_scheme_less_input(self) -> None:
        assert sec._extract_hostname("Example.COM/path") == "example.com"

    def test_extract_hostname_handles_empty_input(self) -> None:
        assert sec._extract_hostname("") == ""

    def test_exact_or_subdomain_prevents_suffix_false_positive(self) -> None:
        assert sec._is_hostname_exact_or_subdomain("api.veritas.com", "veritas.com")
        assert not sec._is_hostname_exact_or_subdomain(
            "evilveritas.com", "veritas.com"
        )


class TestPrivateHostChecks:
    """Branch coverage for private/local detection paths."""

    def test_is_obviously_private_or_local_host_covers_core_cases(self) -> None:
        assert sec._is_obviously_private_or_local_host("localhost")
        assert sec._is_obviously_private_or_local_host("intranet")
        assert sec._is_obviously_private_or_local_host("service.internal")
        assert not sec._is_obviously_private_or_local_host("example.com")

    def test_is_private_or_local_host_returns_false_for_global_dns_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sec,
            "_resolve_host_infos",
            lambda _host: ((None, None, None, None, ("8.8.8.8", 0)),),
        )
        assert sec._is_private_or_local_host("example.com") is False

    def test_is_private_or_local_host_blocks_non_global_dns_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sec,
            "_resolve_host_infos",
            lambda _host: ((None, None, None, None, ("10.0.0.5", 0)),),
        )
        assert sec._is_private_or_local_host("example.com") is True

    def test_is_private_or_local_host_blocks_on_resolution_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_host: str):
            raise socket.gaierror("nope")

        monkeypatch.setattr(sec, "_resolve_host_infos", _boom)
        assert sec._is_private_or_local_host("example.com") is True

    def test_unicode_confusable_hostname_resolution_error_is_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_host: str):
            raise UnicodeError("idna failure")

        monkeypatch.setattr(sec, "_resolve_host_infos", _boom)
        # Fullwidth e + normal rest: confusable with example.com
        assert sec._is_private_or_local_host("ｅxample.com") is True


class TestDnsRebindingHelpers:
    """Coverage for rebinding guard and uncached DNS resolution."""

    def test_resolve_public_ips_uncached_success_deduplicates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sec.socket,
            "getaddrinfo",
            lambda *_a, **_k: [
                (None, None, None, None, ("8.8.8.8", 0)),
                (None, None, None, None, ("8.8.8.8", 443)),
                (None, None, None, None, ("1.1.1.1", 0)),
            ],
        )
        assert sec._resolve_public_ips_uncached("example.com") == {"8.8.8.8", "1.1.1.1"}

    @pytest.mark.parametrize(
        "answer, message",
        [
            ([(None, None, None, None, ("10.0.0.1", 0))], "non-global"),
            ([(None, None, None, None, ("not-an-ip", 0))], "invalid IP"),
            ([], "no valid IPs"),
        ],
    )
    def test_resolve_public_ips_uncached_rejects_invalid_answers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answer,
        message: str,
    ) -> None:
        monkeypatch.setattr(sec.socket, "getaddrinfo", lambda *_a, **_k: answer)
        with pytest.raises(ValueError, match=message):
            sec._resolve_public_ips_uncached("example.com")

    def test_extract_public_ips_for_url_rejects_missing_host(self) -> None:
        with pytest.raises(ValueError, match="no hostname"):
            sec._extract_public_ips_for_url("https:///search")

    def test_validate_rebinding_guard_detects_dns_drift(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_extract_public_ips_for_url", lambda _u: {"8.8.4.4"})
        with pytest.raises(ValueError, match="DNS result changed"):
            sec._validate_rebinding_guard("https://example.com", {"8.8.8.8"})


class TestUrlValidation:
    """URL allow/deny behavior with encoded payload and malformed input."""

    def test_sanitize_websearch_url_rejects_and_accepts_expected_inputs(self) -> None:
        assert sec._sanitize_websearch_url("") == ""
        assert sec._sanitize_websearch_url("http://example.com") == ""
        assert sec._sanitize_websearch_url("https://user:pass@example.com") == ""
        assert sec._sanitize_websearch_url("https:///search") == ""
        assert sec._sanitize_websearch_url("https://example.com/search") == (
            "https://example.com/search"
        )

    def test_is_allowed_websearch_url_with_allowlist_multiple_signal_denial(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: True)
        assert not sec._is_allowed_websearch_url(
            "https://api.allowed.example/search",
            resolve_allowlist_fn=lambda: {"api.allowed.example"},
        )

    def test_is_allowed_websearch_url_false_positive_suppression_for_encoded_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        base64_payload = "SWdub3JlIGFsbCBwcmV2aW91cyBpbnN0cnVjdGlvbnM="
        url_encoded_payload = "%69%67%6e%6f%72%65%20%72%75%6c%65%73"
        url = (
            "https://api.allowed.example/search"
            f"?q={base64_payload}&next={url_encoded_payload}"
        )
        assert sec._is_allowed_websearch_url(
            url,
            resolve_allowlist_fn=lambda: {"api.allowed.example"},
        )

    def test_nfkc_related_fullwidth_dot_hostname_is_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fullwidth-dot host (example．com) is confusable and should be denied.
        def _boom(_host: str):
            raise UnicodeError("idna failure")

        monkeypatch.setattr(sec, "_resolve_host_infos", _boom)
        assert not sec._is_allowed_websearch_url("https://example．com/search")


# ===================================================================
# Adversarial security tests – bypass / failure mode coverage
# ===================================================================


class TestTrailingDotBypass:
    """Trailing dot variations must not escape canonicalization."""

    def test_single_trailing_dot_stripped(self) -> None:
        assert sec._canonicalize_hostname("example.com.") == "example.com"

    def test_multiple_trailing_dots_stripped(self) -> None:
        assert sec._canonicalize_hostname("example.com...") == "example.com"

    def test_extract_hostname_strips_trailing_dot(self) -> None:
        assert sec._extract_hostname("https://example.com./path") == "example.com"

    def test_subdomain_match_with_trailing_dot(self) -> None:
        assert sec._is_hostname_exact_or_subdomain("api.veritas.com.", "veritas.com")

    def test_allowlist_match_with_trailing_dot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        assert sec._is_allowed_websearch_url(
            "https://api.example.com./search",
            resolve_allowlist_fn=lambda: {"api.example.com"},
        )


class TestFullwidthHostnameExtraction:
    """Fullwidth hostname chars must NFKC-normalize in _extract_hostname."""

    def test_fullwidth_hostname_normalized_in_extract(self) -> None:
        # _extract_hostname now applies NFKC via _canonicalize_hostname
        assert sec._extract_hostname("ｅｘａｍｐｌｅ．ｃｏｍ/path") == "example.com"

    def test_fullwidth_in_url_scheme(self) -> None:
        # urlparse won't match the scheme; fallback adds http://
        host = sec._extract_hostname("ｈｔｔｐｓ://ｅｘａｍｐｌｅ.com/p")
        # fullwidth scheme won't parse correctly, but host should normalize
        assert "example" in host or host == ""


class TestZeroWidthCharsInHostname:
    """Zero-width characters injected into hostnames must be stripped."""

    def test_zwsp_in_hostname_stripped(self) -> None:
        # exam\u200bple.com -> example.com after stripping
        assert sec._canonicalize_hostname("exam\u200bple.com") == "example.com"

    def test_zwj_in_hostname_stripped(self) -> None:
        assert sec._canonicalize_hostname("exam\u200dple.com") == "example.com"

    def test_soft_hyphen_in_hostname_stripped(self) -> None:
        assert sec._canonicalize_hostname("exam\u00adple.com") == "example.com"

    def test_bidi_override_in_hostname_stripped(self) -> None:
        assert sec._canonicalize_hostname("\u202eexample.com") == "example.com"

    def test_word_joiner_in_hostname_stripped(self) -> None:
        assert sec._canonicalize_hostname("exam\u2060ple.com") == "example.com"

    def test_bom_in_hostname_stripped(self) -> None:
        assert sec._canonicalize_hostname("\ufeffexample.com") == "example.com"

    def test_mixed_invisible_chars_stripped(self) -> None:
        host = "e\u200bx\u200ca\u200dm\u00adp\u2060l\ufeffe.com"
        assert sec._canonicalize_hostname(host) == "example.com"

    def test_invisible_chars_do_not_trigger_confusable(self) -> None:
        # After stripping, pure ASCII hostname should NOT be flagged
        assert not sec._hostname_has_confusable_chars("exam\u200bple.com")

    def test_invisible_chars_in_private_host_check(self) -> None:
        # localhost with zero-width chars should still be detected
        assert sec._is_obviously_private_or_local_host("local\u200bhost")


class TestInternalPseudoTLDs:
    """Expanded internal TLD blocklist coverage."""

    @pytest.mark.parametrize("tld", [
        ".corp", ".home", ".lan", ".intranet", ".private",
        ".local", ".internal", ".localhost", ".localdomain",
    ])
    def test_internal_tld_blocked(self, tld: str) -> None:
        assert sec._is_obviously_private_or_local_host(f"service{tld}")

    @pytest.mark.parametrize("tld", [
        ".corp", ".home", ".lan", ".intranet", ".private",
    ])
    def test_new_internal_tld_blocked_in_allowed_url(self, tld: str) -> None:
        assert not sec._is_allowed_websearch_url(f"https://api{tld}/search")


class TestSanitizeWebsearchUrlDefenseInDepth:
    """_sanitize_websearch_url now rejects obviously private/local hosts."""

    def test_sanitize_rejects_localhost(self) -> None:
        assert sec._sanitize_websearch_url("https://localhost/search") == ""

    def test_sanitize_rejects_single_label(self) -> None:
        assert sec._sanitize_websearch_url("https://intranet/search") == ""

    def test_sanitize_rejects_private_ip(self) -> None:
        assert sec._sanitize_websearch_url("https://10.0.0.1/search") == ""

    def test_sanitize_rejects_loopback(self) -> None:
        assert sec._sanitize_websearch_url("https://127.0.0.1/search") == ""

    def test_sanitize_rejects_internal_tld(self) -> None:
        assert sec._sanitize_websearch_url("https://api.corp/search") == ""

    def test_sanitize_accepts_public_host(self) -> None:
        assert (
            sec._sanitize_websearch_url("https://api.serper.dev/search")
            == "https://api.serper.dev/search"
        )


class TestCyrillicHomoglyphUrlValidation:
    """Full-path tests for Cyrillic/Greek homoglyph hostnames in URL validation."""

    def test_cyrillic_a_blocked_in_sanitize(self) -> None:
        # Cyrillic а (U+0430) instead of Latin a
        assert sec._sanitize_websearch_url("https://\u0430pple.com/search") == ""

    def test_greek_omicron_blocked_in_sanitize(self) -> None:
        # Greek ο (U+03BF) instead of Latin o
        assert sec._sanitize_websearch_url("https://g\u03bfgle.com/search") == ""

    def test_cyrillic_blocked_in_is_allowed(self) -> None:
        assert not sec._is_allowed_websearch_url("https://\u0430pple.com/search")


class TestEmbeddedCredentialsEdgeCases:
    """Edge cases for embedded credential detection."""

    def test_username_only_in_sanitize(self) -> None:
        assert sec._sanitize_websearch_url("https://user@example.com/search") == ""

    def test_username_only_in_is_allowed(self) -> None:
        assert not sec._is_allowed_websearch_url("https://user@example.com/search")

    def test_empty_password_in_sanitize(self) -> None:
        assert sec._sanitize_websearch_url("https://user:@example.com/search") == ""

    def test_at_sign_in_path_not_blocked(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # @ in path component (not userinfo) should be allowed
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        assert sec._is_allowed_websearch_url("https://example.com/user@host")


class TestIPv6PrivateAddresses:
    """IPv6 loopback and link-local addresses must be blocked."""

    def test_ipv6_loopback_blocked(self) -> None:
        assert sec._is_obviously_private_or_local_host("::1")

    def test_ipv6_link_local_blocked(self) -> None:
        assert sec._is_obviously_private_or_local_host("fe80::1")

    def test_ipv6_private_blocked(self) -> None:
        assert sec._is_obviously_private_or_local_host("fd00::1")

    def test_ipv4_mapped_ipv6_private_blocked(self) -> None:
        # ::ffff:127.0.0.1 is IPv4-mapped IPv6, not global
        assert sec._is_obviously_private_or_local_host("::ffff:127.0.0.1")

    def test_ipv6_in_url_sanitize_blocked(self) -> None:
        assert sec._sanitize_websearch_url("https://[::1]/search") == ""


class TestMalformedUrlEdgeCases:
    """Malformed and edge-case URLs must not bypass validation."""

    def test_none_url_sanitize(self) -> None:
        assert sec._sanitize_websearch_url(None) == ""  # type: ignore[arg-type]

    def test_whitespace_only_url(self) -> None:
        assert sec._sanitize_websearch_url("   ") == ""

    def test_file_scheme_blocked(self) -> None:
        assert sec._sanitize_websearch_url("file:///etc/passwd") == ""
        assert not sec._is_allowed_websearch_url("file:///etc/passwd")

    def test_ftp_scheme_blocked(self) -> None:
        assert not sec._is_allowed_websearch_url("ftp://example.com/file")

    def test_javascript_scheme_blocked(self) -> None:
        assert not sec._is_allowed_websearch_url("javascript:alert(1)")

    def test_data_scheme_blocked(self) -> None:
        assert not sec._is_allowed_websearch_url("data:text/html,<h1>hi</h1>")

    def test_extract_hostname_none_input(self) -> None:
        assert sec._extract_hostname(None) == ""  # type: ignore[arg-type]

    def test_extract_hostname_whitespace_only(self) -> None:
        assert sec._extract_hostname("   ") == ""

    def test_extract_public_ips_empty_url(self) -> None:
        with pytest.raises(ValueError, match="no hostname"):
            sec._extract_public_ips_for_url("")


class TestDnsFailureModes:
    """DNS resolution failure handling – fail-closed behavior."""

    def test_os_error_during_resolution_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(_host: str):
            raise OSError("network unreachable")

        monkeypatch.setattr(sec, "_resolve_host_infos", _boom)
        assert sec._is_private_or_local_host("example.com") is True

    def test_resolve_uncached_os_error_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_a, **_k):
            raise OSError("network unreachable")

        monkeypatch.setattr(sec.socket, "getaddrinfo", _boom)
        with pytest.raises(ValueError, match="not resolvable"):
            sec._resolve_public_ips_uncached("example.com")

    def test_resolve_uncached_unicode_error_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_a, **_k):
            raise UnicodeError("idna encoding failed")

        monkeypatch.setattr(sec.socket, "getaddrinfo", _boom)
        with pytest.raises(ValueError, match="not resolvable"):
            sec._resolve_public_ips_uncached("example.com")

    def test_mixed_global_and_private_ips_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If DNS returns both a global and a private IP, reject."""
        monkeypatch.setattr(
            sec,
            "_resolve_host_infos",
            lambda _host: (
                (None, None, None, None, ("8.8.8.8", 0)),
                (None, None, None, None, ("10.0.0.1", 0)),
            ),
        )
        assert sec._is_private_or_local_host("example.com") is True


class TestAllowlistCanonicalizationBypass:
    """Allowlist matching must use canonicalized hostnames."""

    def test_trailing_dot_matches_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        # URL has trailing dot, allowlist doesn't
        assert sec._is_allowed_websearch_url(
            "https://api.example.com./search",
            resolve_allowlist_fn=lambda: {"api.example.com"},
        )

    def test_case_insensitive_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        assert sec._is_allowed_websearch_url(
            "https://API.EXAMPLE.COM/search",
            resolve_allowlist_fn=lambda: {"api.example.com"},
        )

    def test_non_allowlisted_host_denied_even_if_public(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sec, "_is_private_or_local_host", lambda _h: False)
        assert not sec._is_allowed_websearch_url(
            "https://evil.com/search",
            resolve_allowlist_fn=lambda: {"api.example.com"},
        )


class TestRebindingGuardEdgeCases:
    """Edge cases for the DNS rebinding guard."""

    def test_rebinding_guard_superset_ips_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If current DNS returns MORE IPs than expected, flag as drift."""
        monkeypatch.setattr(
            sec, "_extract_public_ips_for_url", lambda _u: {"8.8.8.8", "1.1.1.1"}
        )
        with pytest.raises(ValueError, match="DNS result changed"):
            sec._validate_rebinding_guard("https://example.com", {"8.8.8.8"})

    def test_rebinding_guard_subset_ips_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If current DNS returns FEWER IPs than expected, flag as drift."""
        monkeypatch.setattr(
            sec, "_extract_public_ips_for_url", lambda _u: {"8.8.8.8"}
        )
        with pytest.raises(ValueError, match="DNS result changed"):
            sec._validate_rebinding_guard(
                "https://example.com", {"8.8.8.8", "1.1.1.1"}
            )

    def test_rebinding_guard_exact_match_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sec, "_extract_public_ips_for_url", lambda _u: {"8.8.8.8", "1.1.1.1"}
        )
        # Should not raise
        sec._validate_rebinding_guard(
            "https://example.com", {"8.8.8.8", "1.1.1.1"}
        )
