"""SSE event hub utilities for API server event streaming.

This module isolates event-stream state management from ``api/server.py``
to keep bootstrap and route logic focused on HTTP concerns.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from collections import deque
from typing import Any, Callable, Dict


logger = logging.getLogger(__name__)


class SSEEventHub:
    """In-memory SSE event hub with bounded history and subscriber queues."""

    def __init__(
        self,
        timestamp_factory: Callable[[], str],
        history_size: int = 128,
        queue_size: int = 64,
    ) -> None:
        self._timestamp_factory = timestamp_factory
        self._queue_size = queue_size
        self._lock = threading.Lock()
        self._history = deque(maxlen=history_size)
        self._subscribers: set[queue.Queue] = set()
        self._seq = 0

    def publish(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Publish one event to all subscribers and keep it in short history."""
        with self._lock:
            self._seq += 1
            event = {
                "id": self._seq,
                "type": event_type,
                "ts": self._timestamp_factory(),
                "payload": payload,
            }
            self._history.append(event)
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(event)
            except queue.Full:
                logger.debug("sse queue full; dropping event for a slow subscriber")
            except Exception:
                logger.debug("failed to push sse event", exc_info=True)
        return event

    def register(self) -> queue.Queue:
        """Register a subscriber queue and pre-fill it with recent history."""
        subscriber: queue.Queue = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            history = list(self._history)
            self._subscribers.add(subscriber)

        for item in history:
            try:
                subscriber.put_nowait(item)
            except queue.Full:
                break
        return subscriber

    def unregister(self, subscriber: queue.Queue) -> None:
        """Remove a subscriber queue safely."""
        with self._lock:
            self._subscribers.discard(subscriber)


def publish_event_best_effort(
    event_hub: SSEEventHub,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """Publish an SSE event without raising exceptions to callers."""
    try:
        event_hub.publish(event_type=event_type, payload=payload)
    except Exception:
        logger.debug("failed to publish sse event", exc_info=True)


def format_sse_message(event: Dict[str, Any]) -> str:
    """Format one SSE event frame."""
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {data}\n\n"

