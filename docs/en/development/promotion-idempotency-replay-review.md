# Promotion idempotency and replay review

After a passing Runtime Risk Review, call
`review_promotion_idempotency_and_replay` in
`veritas_os.policy.live_adapter_bind_authorization_requirements` with the risk
packet, its full final credential-scope source, and an aware `reviewed_at`.
The function independently verifies the source and requires the review time
to be within the remaining risk window (expiry is exclusive).

The returned immutable model serializes with `model_dump(mode="json")`.
Verify it with `verify_promotion_idempotency_replay_review`, supplying both
independent sources and a trusted current `now`. Verification reconstructs
every field and checks expiry again. A digest is integrity evidence, not a
signature or evidence that an authorization is unused.

This stage reviews the required replay policy and existing implementation
owners. It does not query a store or reserve a key. The final authorization
key still requires the signed authorization decision and validity interval;
it remains owned by `live_adapter_bind_authorization_checks`. Atomic single-use
consumption remains mandatory before credential resolution and dispatch.
Runtime Bind risk checks remain mandatory. A passing artifact advances only
to signed gate-bound human approval issuance; it grants no execution authority.

This is a callable composition boundary, not automatic runtime integration.
Tests in `test_promotion_idempotency_replay_review.py` include serialization,
tampering, blocked/missing risk signals, and temporal boundary checks.
