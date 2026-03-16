"""Article 14 human oversight helpers for EU AI Act compliance.

Extracted from ``eu_ai_act_compliance_module.py`` for maintainability.

Covers:
- ``HumanReviewQueue`` — thread-safe review queue with SLA tracking (P1-3).
- ``SystemHaltController`` — Art. 14(4) emergency stop mechanism.
- ``apply_human_oversight_hook()`` — pause logic for high-risk / low-trust.
- ``DEFAULT_HUMAN_REVIEW_SLA_SECONDS`` constant.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, MutableMapping

from veritas_os.core.eu_ai_act_prohibited import EUComplianceConfig  # noqa: F811 — will be moved

logger = logging.getLogger(__name__)

# Default SLA for human review: 4 hours (14400 seconds)
DEFAULT_HUMAN_REVIEW_SLA_SECONDS = 14400


# ---------------------------------------------------------------------------
# P1-3: Human Review Queue (Art. 14 workflow implementation)
# ---------------------------------------------------------------------------
class HumanReviewQueue:
    """Thread-safe in-process human-review queue.

    Art. 14 Human Oversight — P1-3:
    Provides queue storage, SLA deadline tracking, webhook notification hooks,
    and override prevention.

    In production deployments this should be backed by an external message
    broker (Redis / SQS / etc.).  The interface is designed so that a swap
    requires only a new backend adapter — no caller changes.
    """

    _lock = threading.Lock()
    _queue: List[Dict[str, Any]] = []
    _webhook_url: str | None = os.environ.get("VERITAS_HUMAN_REVIEW_WEBHOOK_URL")
    _sla_seconds: int = int(
        os.environ.get("VERITAS_HUMAN_REVIEW_SLA_SECONDS", str(DEFAULT_HUMAN_REVIEW_SLA_SECONDS))
    )

    @classmethod
    def enqueue(
        cls,
        *,
        decision_payload: Dict[str, Any],
        reason: str = "",
    ) -> Dict[str, Any]:
        """Add a decision to the human-review queue.

        Returns the queue entry (contains entry_id, sla_deadline, etc.).
        """
        entry_id = hashlib.sha256(
            json.dumps(decision_payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        entry: Dict[str, Any] = {
            "entry_id": entry_id,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
            "sla_deadline": datetime.fromtimestamp(
                time.time() + cls._sla_seconds, tz=timezone.utc
            ).isoformat(),
            "sla_seconds": cls._sla_seconds,
            "status": "pending",
            "reason": reason,
            "payload_summary": {
                "request_id": decision_payload.get("request_id", ""),
                "risk_level": decision_payload.get("eu_risk_assessment", {}).get("risk_level", ""),
            },
            "reviewer": None,
            "reviewed_at": None,
            "decision": None,
        }

        with cls._lock:
            cls._queue.append(entry)

        # Fire webhook notification (best-effort)
        cls._notify_webhook(entry)

        logger.info(
            "Human-review entry queued: entry_id=%s sla=%ss reason=%s",
            entry_id,
            cls._sla_seconds,
            reason,
        )
        return entry

    @classmethod
    def review(
        cls,
        entry_id: str,
        *,
        approved: bool,
        reviewer: str,
        comment: str = "",
    ) -> Dict[str, Any] | None:
        """Record a human review decision.  Returns the updated entry or None."""
        with cls._lock:
            for entry in cls._queue:
                if entry["entry_id"] == entry_id and entry["status"] == "pending":
                    entry["status"] = "approved" if approved else "rejected"
                    entry["reviewer"] = reviewer
                    entry["reviewed_at"] = datetime.now(timezone.utc).isoformat()
                    entry["decision"] = "approved" if approved else "rejected"
                    entry["comment"] = comment
                    return dict(entry)
        return None

    @classmethod
    def pending_entries(cls) -> List[Dict[str, Any]]:
        """Return a snapshot of all pending review entries."""
        with cls._lock:
            return [dict(e) for e in cls._queue if e["status"] == "pending"]

    @classmethod
    def get_entry(cls, entry_id: str) -> Dict[str, Any] | None:
        """Look up a single queue entry by ID."""
        with cls._lock:
            for entry in cls._queue:
                if entry["entry_id"] == entry_id:
                    return dict(entry)
        return None

    @classmethod
    def _notify_webhook(cls, entry: Dict[str, Any]) -> None:
        """Best-effort webhook notification for new review entries."""
        url = cls._webhook_url
        if not url:
            return
        # Validate URL scheme to prevent SSRF
        if not url.startswith(("https://", "http://")):
            logger.warning("Webhook URL has unsupported scheme, skipping: %s", url[:30])
            return
        try:
            import urllib.request
            data = json.dumps(
                {"event": "human_review_required", "entry": entry},
                default=str,
            ).encode()
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)  # nosec B310
        except Exception:
            logger.debug("Webhook notification failed for entry %s", entry.get("entry_id"), exc_info=True)

    @classmethod
    def check_expired_entries(cls) -> List[Dict[str, Any]]:
        """Identify and mark pending entries that have exceeded SLA deadline.

        Art. 14 Human Oversight — GAP-14:
        Entries that exceed their SLA deadline are marked ``expired`` so that
        downstream systems can escalate or block the decision.

        Returns:
            List of newly-expired entries.
        """
        now = datetime.now(timezone.utc)
        expired: List[Dict[str, Any]] = []
        with cls._lock:
            for entry in cls._queue:
                if entry["status"] != "pending":
                    continue
                deadline_str = entry.get("sla_deadline", "")
                if not deadline_str:
                    continue
                try:
                    deadline = datetime.fromisoformat(deadline_str)
                except (TypeError, ValueError):
                    continue
                if now >= deadline:
                    entry["status"] = "expired"
                    entry["expired_at"] = now.isoformat()
                    expired.append(dict(entry))
        for e in expired:
            logger.warning(
                "Human-review entry expired (SLA breached): entry_id=%s deadline=%s",
                e.get("entry_id"),
                e.get("sla_deadline"),
            )
            cls._notify_webhook({**e, "event_type": "sla_expired"})
        return expired

    @classmethod
    def clear_for_testing(cls) -> None:
        """Clear the queue (test helper only)."""
        with cls._lock:
            cls._queue.clear()


# ---------------------------------------------------------------------------
# Art. 14(4): System halt / emergency stop controller
# ---------------------------------------------------------------------------
class SystemHaltController:
    """Thread-safe emergency stop mechanism for human operators.

    Art. 14(4) requires that natural persons assigned to human oversight
    can *interrupt, suspend, or halt* the AI system when necessary.

    This controller provides a global halted flag that the compliance
    pipeline checks before executing any decision.  When halted, all
    new ``/v1/decide`` requests are refused with an explicit status.

    In production, integrate with your orchestration layer so that
    halt/resume actions are audit-logged and permission-gated.
    """

    _lock = threading.Lock()
    _halted: bool = False
    _halted_by: str | None = None
    _halted_at: str | None = None
    _halt_reason: str | None = None
    _history: List[Dict[str, Any]] = []

    @classmethod
    def halt(cls, *, reason: str, operator: str) -> Dict[str, Any]:
        """Halt the AI decision system.

        Args:
            reason: Human-readable explanation for the halt.
            operator: Identifier of the person initiating the halt.

        Returns:
            Dict with halt confirmation details.
        """
        now = datetime.now(timezone.utc).isoformat()
        with cls._lock:
            cls._halted = True
            cls._halted_by = operator
            cls._halted_at = now
            cls._halt_reason = reason
            cls._history.append({
                "action": "halt",
                "operator": operator,
                "reason": reason,
                "timestamp": now,
            })
        logger.warning(
            "System HALTED by %s: %s", operator, reason,
        )
        return {
            "halted": True,
            "halted_by": operator,
            "halted_at": now,
            "reason": reason,
        }

    @classmethod
    def resume(cls, *, operator: str, comment: str = "") -> Dict[str, Any]:
        """Resume the AI decision system after a halt.

        Args:
            operator: Identifier of the person resuming the system.
            comment: Optional comment explaining the resumption.

        Returns:
            Dict with resume confirmation details.
        """
        now = datetime.now(timezone.utc).isoformat()
        with cls._lock:
            was_halted = cls._halted
            cls._halted = False
            cls._halted_by = None
            cls._halted_at = None
            cls._halt_reason = None
            cls._history.append({
                "action": "resume",
                "operator": operator,
                "comment": comment,
                "timestamp": now,
            })
        logger.info("System RESUMED by %s: %s", operator, comment)
        return {
            "resumed": True,
            "was_halted": was_halted,
            "resumed_by": operator,
            "resumed_at": now,
        }

    @classmethod
    def is_halted(cls) -> bool:
        """Return ``True`` if the system is currently halted."""
        with cls._lock:
            return cls._halted

    @classmethod
    def status(cls) -> Dict[str, Any]:
        """Return the current halt status for dashboards and health checks."""
        with cls._lock:
            return {
                "halted": cls._halted,
                "halted_by": cls._halted_by,
                "halted_at": cls._halted_at,
                "reason": cls._halt_reason,
            }

    @classmethod
    def clear_for_testing(cls) -> None:
        """Reset state (test helper only)."""
        with cls._lock:
            cls._halted = False
            cls._halted_by = None
            cls._halted_at = None
            cls._halt_reason = None
            cls._history.clear()


def apply_human_oversight_hook(
    *,
    trust_score: float,
    risk_level: str,
    response_payload: MutableMapping[str, Any],
    threshold: float = 0.8,
    config: EUComplianceConfig | None = None,
) -> Dict[str, Any]:
    """Apply human-in-the-loop pause logic.

    Art. 14 Human Oversight:
        Force pause when confidence is low or decision context is high-risk.

    P1-3: Queue entry, webhook notification, SLA timeout management.
    P1-6: Fail-close — when human review is required the decision is blocked
    until a human approves.  Subsequent automatic processes cannot override.
    """
    cfg = config or EUComplianceConfig()
    should_pause = float(trust_score) < threshold or (risk_level or "").upper() == "HIGH"
    if should_pause:
        response_payload["status"] = "PENDING_HUMAN_REVIEW"
        response_payload["paused_by"] = "Art.14_human_oversight_hook"

        # P1-3: Enqueue for human review with SLA metadata
        entry = HumanReviewQueue.enqueue(
            decision_payload=dict(response_payload),
            reason=f"trust_score={trust_score:.2f}, risk_level={risk_level}",
        )
        response_payload["human_review_entry_id"] = entry["entry_id"]
        response_payload["human_review_sla_deadline"] = entry["sla_deadline"]

        # P1-6: Fail-close — mark decision as blocked to prevent auto-override
        if cfg.fail_close:
            response_payload["decision_blocked"] = True
            response_payload["fail_close"] = True
            response_payload["decision_status"] = "hold"

    return dict(response_payload)
