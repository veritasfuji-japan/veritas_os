# Persistent Replay Audit Registry: Proposed Contract v0.1 (design only)

**Status:** design and offline candidate-record validation. **No persistent registry implementation, database migration, ingestion API, runtime admission, trusted provenance, external timestamping, custody, or certification is introduced by this PR.**

## Motivation and existing boundaries

- PR #2446 provides `verify_cross_packet_replay_provenance`: a deterministic, read-only scan of explicitly supplied v0.2 Audit Evidence Profile packets. Its `PASS` means local self-consistency **within that supplied set**, not that every historical packet was seen.
- The separate Real Bind Authorization consumption gate already has a PostgreSQL-backed atomic single-use implementation (`docs/en/architecture/live-adapter-bind-authorization-consumption-v1.md`). This proposal neither replaces nor extends that effect-side authority mechanism.
- The proposed audit registry would retain **audit observations** across independent scan invocations. This is a retrospective audit-inventory capability and cannot grant, consume, or authorize a live action.

## This PR's deliverables

1. `schemas/veritas_audit_replay_observation_v0_1.schema.json`: bounded, versioned record format with explicit unauthenticated/local-only fields.
2. `scripts/validation/validate_audit_replay_observation_v0_1.py`: pure, read-only schema and self-integrity checker, returning deterministic errors.
3. `tests/validation/test_audit_replay_observation_v0_1.py` and isolated CI: synthetic positive/negative checks.

No code in this PR writes an observation to disk or PostgreSQL. A candidate record passing format validation is **not registered** and has **not been looked up against previous history**.

## Candidate record fields and semantics

| Field(s) | Source and meaning |
| --- | --- |
| `packet_id`, `case_id` | v0.2 Profile and cross-packet scan link; one future observation per bound case |
| `repository_claim` | Profile `scope.repository`, a **self-declared** GitHub-style owner/repo name |
| `repository_key` | ASCII lowercase of `repository_claim`, used only for deterministic equality within a **claimed** namespace |
| `operation_id`, `manifest_id`, `manifest_sha256` | Case and locally checked canonical Manifest identity and bytes |
| `profile_sha256` | Raw local Profile bytes digest from the scanner's packet record |
| `source_commit` | Profile's declared 40-character Git commit ID, **not verified against GitHub** |
| `snapshot_digest` | Digest of the explicit scan inventory; **not externally anchored** |
| `local_manifest_binding` | Fixed `MATCHED`, a claimed local binding context |
| `declared_provenance_binding` | Fixed `CLAIMED_CONTEXT_MATCHES_LOCAL_MANIFEST`, **not authenticated origin** |
| `origin_authentication`, `independent_review` | Fixed `NOT_PERFORMED`; elevated values are rejected |
| `record_hash` | SHA-256 over `sha256_of_canonical_json` of all fields **except** `record_hash` |

The hash uses VERITAS's existing sorted-key, compact UTF-8 JSON canonicalization helper. It catches accidental or uncoordinated changes to a record, but an attacker who edits the record may recompute it. An unsigned hash is **not** a signature, a secure clock, a trusted database transaction or a tamper-proof history.

The v0.1 candidate requires ASCII `owner/repo` names, using a lowercased **claimed** repository key for cross-packet comparisons; the format validator rejects mismatches and unsupported namespaces. It does not establish tenant ownership. Unsupported repository claims must fail closed rather than be silently mapped to an arbitrary tenant.

## Future ingest interface (not implemented)

A subsequent PR may implement:

1. Resolve an explicit packet set from a trusted, isolated input root and **re-run** PR #2446's scanner; never trust a caller-provided `PASS`, a raw observation record, a self-reported repository key, or a supplied hash as authoritative.
2. Require a complete local `PASS` scan of the intended input set and ensure each observation exactly matches the scanner's `packet_records`, `link_records` and `snapshot_digest`. On missing/unbound/incomplete cases, input mutation or verifier failure, do not persist a success decision.
3. In a single PostgreSQL transaction, insert the packet envelope and **all** of its bound cases under database-enforced unique constraints. Cross-packet replay conflicts cause the entire attempted packet insert to fail. No partial success or check-then-insert time-of-check/time-of-use race.
4. Explicitly report `NEW_OBSERVATION`, `ALREADY_PRESENT`, `REPLAY_DETECTED`, `INPUT_INVALID` or `REGISTRY_UNAVAILABLE`. Identical retries may be marked `ALREADY_PRESENT`, never counted as a new independent observation or a successful fresh single-use admission.
5. Read back retained observations after restart to demonstrate historical duplicate detection. Storage downtime or unverified history is **not** a clean `PASS`; report `REGISTRY_UNAVAILABLE` or `INCOMPLETE` as appropriate.

**Illustrative relational constraints, not a migration:**

    audit_packet_inventory:
      PRIMARY KEY (packet_id)
      profile_sha256, repository_claim, repository_key, source_commit, snapshot_digest

    audit_case_observations:
      PRIMARY KEY (record_hash)
      FOREIGN KEY (packet_id) REFERENCES audit_packet_inventory(packet_id)
      UNIQUE (packet_id, case_id)
      UNIQUE (repository_key, operation_id)
      UNIQUE (repository_key, manifest_id)
      UNIQUE (manifest_sha256)  -- global across repository names

A packet may have multiple cases: `packet_id` is unique **in the packet table**, not across all case rows. The future implementation must check collisions and write every case in one atomic transaction. The system must not trust the claimed repository string for security isolation; if tenant isolation is needed, that boundary requires a separately authenticated principal.

## Threat model and acceptance limits

- **Omitted history:** a registry can only compare against history actually ingested and retained. A global completeness claim additionally requires authoritative packet enumeration, trusted checkpoints, retention and independently checked continuity.
- **Forged provenance:** a malicious author can create a plausible profile, manifest, snapshot and record hash. No issuer signature, repository authenticity, custody or observed effect is established by this contract.
- **Lost, altered or rolled-back storage:** unique constraints alone do not make storage append-only. The future store needs migration safety, backups, privileged-write controls, recovery/rollback tests, independently anchored commitments and read-back verification before tamper resistance can be assessed.
- **Concurrent ingestion:** the future datastore must use transaction-level uniqueness, not a process-local mutex or a separate pre-insert read. Contention requires real PostgreSQL testing, not only mocks.
- **Runtime enforcement:** audit observation storage must never be used as the authority to issue or consume a live Bind permit. Existing production Bind Authorization consumption is a **different** scope and trust boundary.
- **Outage:** audit unavailability must never be presented as clean history. This PR neither changes the runtime gate's failure policy nor claims global bypass resistance.

## Merge gate for this design-only PR

- Schema-valid synthetic candidate with correct self-hash passes local format checks only.
- Wrong schema/version/type/hash, forged elevated trust claims, malformed or mismatched namespace and rehashed invalid values fail.
- Existing Audit Evidence Profile v0.1/v0.2 and Cross-Packet Replay regressions remain green.
- Final-head security/CI workflows succeed and reviewers accept the explicitly **non-persistent, non-authoritative, non-runtime** boundary.

## Proposed subsequent PRs

- **Implementation A:** PostgreSQL migration + atomic archive of full packet and case records, real concurrency and restart tests.
- **Implementation B:** historical comparison/read-back, incomplete history and recovery/rollback test matrix, with bounded pagination and coverage watermark design.
- **Implementation C:** optional independent signature/custody/checkpoint anchors; only after external trust assumptions and reviewer ownership are specified.

Nothing in this design-only change should be described as production-ready replay prevention or externally verified provenance.
