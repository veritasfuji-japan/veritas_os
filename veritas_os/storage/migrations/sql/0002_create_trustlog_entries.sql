-- 0002_create_trustlog_entries.sql
-- Initial schema for the PostgreSQL TrustLogStore backend.
-- Idempotent: uses IF NOT EXISTS for all objects.

CREATE TABLE IF NOT EXISTS trustlog_entries (
    id          BIGSERIAL   PRIMARY KEY,
    request_id  TEXT        NOT NULL UNIQUE,
    entry       JSONB       NOT NULL DEFAULT '{}',
    hash        TEXT,
    prev_hash   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Lookup by request_id (unique already creates an index, but explicit
-- naming improves operational clarity).
CREATE INDEX IF NOT EXISTS ix_trustlog_entries_request_id
    ON trustlog_entries (request_id);

-- Time-ordered scans / pagination.
CREATE INDEX IF NOT EXISTS ix_trustlog_entries_created_at
    ON trustlog_entries (created_at);

-- ───────────────────────────────────────────────────────────────
-- Lightweight chain-state tracker (single-row table).
-- Stores the most-recent hash so that the application can
-- resume hash-chain construction after restart without scanning
-- the entire trustlog_entries table.
-- ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trustlog_chain_state (
    id          INTEGER     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_hash   TEXT,
    last_id     BIGINT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
