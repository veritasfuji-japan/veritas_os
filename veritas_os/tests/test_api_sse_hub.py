from __future__ import annotations

from veritas_os.api.sse_hub import (
    SSEEventHub,
    format_sse_message,
    publish_event_best_effort,
)


def test_sse_event_hub_register_prefills_history() -> None:
    hub = SSEEventHub(timestamp_factory=lambda: "2026-03-16T00:00:00Z", history_size=4)
    hub.publish(event_type="decide", payload={"id": "d-1"})

    subscriber = hub.register()
    prefilled = subscriber.get_nowait()

    assert prefilled["id"] == 1
    assert prefilled["type"] == "decide"
    assert prefilled["payload"]["id"] == "d-1"


def test_sse_event_hub_unregister_removes_queue() -> None:
    hub = SSEEventHub(timestamp_factory=lambda: "2026-03-16T00:00:00Z")
    subscriber = hub.register()
    hub.unregister(subscriber)

    hub.publish(event_type="audit", payload={"ok": True})

    assert subscriber.empty()


def test_publish_event_best_effort_ignores_internal_errors() -> None:
    class BrokenHub:
        def publish(self, event_type: str, payload: dict) -> None:
            raise RuntimeError("boom")

    publish_event_best_effort(BrokenHub(), event_type="x", payload={"y": 1})


def test_format_sse_message_includes_expected_fields() -> None:
    message = format_sse_message(
        {
            "id": 9,
            "type": "runtime",
            "ts": "2026-03-16T00:00:00Z",
            "payload": {"x": 1},
        }
    )

    assert "id: 9" in message
    assert "event: runtime" in message
    assert '"payload":{"x":1}' in message
