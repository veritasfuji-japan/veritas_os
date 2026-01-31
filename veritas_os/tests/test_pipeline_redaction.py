from veritas_os.core import pipeline


def test_redact_payload_masks_pii():
    payload = {
        "query": "Reach me at test@example.com or 090-1234-5678.",
        "count": 1,
        "nested": [{"note": "Alt: test@example.com"}],
    }

    redacted = pipeline.redact_payload(payload)

    assert "test@example.com" not in redacted["query"]
    assert "090-1234-5678" not in redacted["query"]
    assert "test@example.com" not in redacted["nested"][0]["note"]
