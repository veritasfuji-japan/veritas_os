-- 0001_create_memory_records.sql
-- Initial schema for the PostgreSQL MemoryStore backend.
-- Idempotent: uses IF NOT EXISTS for all objects.

CREATE TABLE IF NOT EXISTS memory_records (
    id          BIGSERIAL PRIMARY KEY,
    key         TEXT        NOT NULL,
    user_id     TEXT        NOT NULL,
    value       JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enforce one row per (key, user_id) — upsert-friendly.
CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_records_key_user
    ON memory_records (key, user_id);

-- Fast user-scoped listing / erasure.
CREATE INDEX IF NOT EXISTS ix_memory_records_user_id
    ON memory_records (user_id);

-- GIN index for JSONB full-text / containment queries.
CREATE INDEX IF NOT EXISTS ix_memory_records_value_gin
    ON memory_records USING gin (value);
