"""PostgreSQL-backed governance repository implementation.

This repository stores governance policy snapshots, policy change events,
and event-scoped approvals in PostgreSQL while preserving the existing
repository contract used by the API layer.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from veritas_os.governance.models import GovernancePolicyEventRecord
from veritas_os.governance.repository import GovernanceRepository


class PostgresGovernanceRepository(GovernanceRepository):
    """PostgreSQL-backed repository for governance policy state and history."""

    def __init__(self, *, database_url: str | None = None) -> None:
        self._database_url = database_url

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        """Open a transaction-capable psycopg connection."""
        from veritas_os.storage.db import build_conninfo

        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "psycopg is required for PostgresGovernanceRepository"
            ) from exc

        dsn = self._database_url or build_conninfo()
        conn = psycopg.connect(dsn)
        try:
            yield conn
        finally:
            conn.close()

    def get_current_policy(
        self,
        *,
        default_factory: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT policy_payload FROM governance_policies "
                    "WHERE is_current = TRUE LIMIT 1"
                )
                row = cur.fetchone()
                if row is None:
                    conn.rollback()
                    return default_factory()
                payload = row[0]
                conn.rollback()
                return payload if isinstance(payload, dict) else default_factory()

    def save_policy(self, policy: dict[str, Any]) -> None:
        self.update_policy(
            previous={},
            updated=policy,
            proposer=str(policy.get("updated_by", "unknown")),
            approvers=[],
            event_type="save",
            approval_records=[],
        )

    def append_policy_event(self, event: GovernancePolicyEventRecord) -> None:
        # Keep this helper for interface parity; insert event-only row.
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance_policy_events (
                        event_type,
                        previous_policy_id,
                        new_policy_id,
                        previous_digest,
                        new_digest,
                        proposer,
                        changed_by,
                        changed_at,
                        reason,
                        metadata_json
                    ) VALUES (%s, NULL, NULL, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.event_type,
                        event.previous_digest,
                        event.new_digest,
                        event.proposer,
                        event.changed_by,
                        self._parse_timestamp(event.changed_at),
                        "",
                        {
                            "previous_version": event.previous_version,
                            "new_version": event.new_version,
                        },
                    ),
                )
            conn.commit()

    def list_policy_history(self, *, limit: int, max_records: int) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, max_records))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        e.id,
                        e.event_type,
                        e.previous_digest,
                        e.new_digest,
                        e.proposer,
                        e.changed_by,
                        e.changed_at,
                        e.reason,
                        COALESCE(p_prev.policy_payload, '{}'::jsonb) AS previous_policy,
                        COALESCE(p_new.policy_payload, '{}'::jsonb) AS new_policy
                    FROM governance_policy_events e
                    LEFT JOIN governance_policies p_prev ON p_prev.id = e.previous_policy_id
                    LEFT JOIN governance_policies p_new ON p_new.id = e.new_policy_id
                    ORDER BY e.event_order DESC
                    LIMIT %s
                    """,
                    (bounded_limit,),
                )
                rows = cur.fetchall()

                event_ids = [row[0] for row in rows]
                approvals_by_event: dict[int, list[dict[str, str]]] = {}
                if event_ids:
                    cur.execute(
                        """
                        SELECT event_id, reviewer, signature
                        FROM governance_approvals
                        WHERE event_id = ANY(%s)
                        ORDER BY event_id, id
                        """,
                        (event_ids,),
                    )
                    for event_id, reviewer, signature in cur.fetchall():
                        approvals_by_event.setdefault(event_id, []).append(
                            {"reviewer": reviewer, "signature": signature}
                        )

                conn.rollback()

        records: list[dict[str, Any]] = []
        for (
            event_id,
            event_type,
            previous_digest,
            new_digest,
            proposer,
            changed_by,
            changed_at,
            reason,
            previous_policy,
            new_policy,
        ) in rows:
            approvals = approvals_by_event.get(event_id, [])
            records.append(
                {
                    "changed_at": self._as_iso_utc(changed_at),
                    "changed_by": changed_by,
                    "proposer": proposer,
                    "approvers": [item["reviewer"] for item in approvals],
                    "approvals": approvals,
                    "event_type": event_type,
                    "previous_digest": previous_digest,
                    "new_digest": new_digest,
                    "previous_policy": previous_policy,
                    "new_policy": new_policy,
                    "reason": reason,
                }
            )
        return records

    def update_policy(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        self._write_policy_event(
            previous=previous,
            updated=updated,
            proposer=proposer,
            approvers=approvers,
            event_type=event_type,
            approval_records=approval_records,
            reason=reason,
        )

    def rollback_policy(
        self,
        *,
        previous: dict[str, Any],
        restored: dict[str, Any],
        proposer: str,
        approvers: list[str],
        approval_records: list[dict[str, str]] | None = None,
        reason: str = "",
    ) -> None:
        self._write_policy_event(
            previous=previous,
            updated=restored,
            proposer=proposer,
            approvers=approvers,
            event_type="rollback",
            approval_records=approval_records,
            reason=reason,
        )

    def _write_policy_event(
        self,
        *,
        previous: dict[str, Any],
        updated: dict[str, Any],
        proposer: str,
        approvers: list[str],
        event_type: str,
        approval_records: list[dict[str, str]] | None,
        reason: str,
    ) -> None:
        from veritas_os.policy.governance_identity import compute_governance_digest

        normalized_approvals = self._normalize_approvals(
            approvers=approvers,
            approval_records=approval_records,
        )

        prev_digest = compute_governance_digest(previous) if previous else ""
        new_digest = compute_governance_digest(updated)
        changed_by = str(updated.get("updated_by") or proposer or "unknown")
        changed_at = self._parse_timestamp(updated.get("updated_at"))

        with self._connect() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM governance_policies "
                        "WHERE is_current = TRUE "
                        "ORDER BY id DESC LIMIT 1 FOR UPDATE"
                    )
                    row = cur.fetchone()
                    previous_policy_id = row[0] if row is not None else None

                    if previous_policy_id is not None:
                        cur.execute(
                            "UPDATE governance_policies SET is_current = FALSE "
                            "WHERE id = %s",
                            (previous_policy_id,),
                        )

                    cur.execute(
                        """
                        INSERT INTO governance_policies (
                            policy_version,
                            policy_payload,
                            digest,
                            updated_at,
                            updated_by,
                            is_current,
                            policy_revision,
                            metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
                        RETURNING id
                        """,
                        (
                            str(updated.get("version", "")),
                            updated,
                            new_digest,
                            changed_at,
                            changed_by,
                            int(updated.get("policy_revision", 1)),
                            {},
                        ),
                    )
                    new_policy_id = cur.fetchone()[0]

                    cur.execute(
                        """
                        INSERT INTO governance_policy_events (
                            event_type,
                            previous_policy_id,
                            new_policy_id,
                            previous_digest,
                            new_digest,
                            proposer,
                            changed_by,
                            changed_at,
                            reason,
                            metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            event_type,
                            previous_policy_id,
                            new_policy_id,
                            prev_digest,
                            new_digest,
                            proposer,
                            changed_by,
                            changed_at,
                            reason,
                            {
                                "previous_version": previous.get("version"),
                                "new_version": updated.get("version"),
                            },
                        ),
                    )
                    event_id = cur.fetchone()[0]

                    for approval in normalized_approvals:
                        cur.execute(
                            """
                            INSERT INTO governance_approvals (
                                event_id,
                                reviewer,
                                signature,
                                metadata_json
                            ) VALUES (%s, %s, %s, %s)
                            """,
                            (
                                event_id,
                                approval["reviewer"],
                                approval["signature"],
                                {},
                            ),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _normalize_approvals(
        self,
        *,
        approvers: list[str],
        approval_records: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        records = approval_records or [
            {"reviewer": reviewer, "signature": ""}
            for reviewer in approvers
        ]
        normalized: list[dict[str, str]] = []
        seen_reviewers: set[str] = set()
        for item in records:
            reviewer = str(item.get("reviewer", "")).strip()
            signature = str(item.get("signature", "")).strip()
            if not reviewer:
                raise ValueError("approval reviewer must be non-empty")
            if reviewer in seen_reviewers:
                raise ValueError("duplicate approval reviewer is not allowed")
            seen_reviewers.add(reviewer)
            normalized.append({"reviewer": reviewer, "signature": signature})
        return normalized

    @staticmethod
    def _parse_timestamp(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw.astimezone(timezone.utc)
        if isinstance(raw, str) and raw.strip():
            candidate = raw.strip().replace("Z", "+00:00")
            return datetime.fromisoformat(candidate).astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    @staticmethod
    def _as_iso_utc(value: Any) -> str:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return str(value)
