from __future__ import annotations

import logging

from veritas_os.core import config


def test_parse_cors_origins_ignores_wildcard(caplog):
    caplog.set_level(logging.WARNING)

    origins = config._parse_cors_origins("https://example.com, *")

    assert origins == ["https://example.com"]
    assert "ignored for safety" in caplog.text
