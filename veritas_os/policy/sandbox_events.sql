-- Install only in a dedicated sandbox database. Not a main-API migration.
-- A row is both the event effect and its immutable operation record.
CREATE TABLE sandbox_events (
    operation_id UUID PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE
        CHECK (length(idempotency_key) BETWEEN 1 AND 256
               AND idempotency_key ~ '^[A-Za-z0-9._:-]+$'),
    event_id UUID NOT NULL UNIQUE,
    message TEXT NOT NULL CHECK (octet_length(message) BETWEEN 1 AND 256),
    payload_digest TEXT NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$')
);
-- Runtime writer: SELECT, INSERT only. Reconciler DB role: SELECT only.
-- No TTL/deletion while any operation may remain unknown.
