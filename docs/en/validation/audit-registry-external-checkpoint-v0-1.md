# Audit Registry External Checkpoint v0.1 — independent-pin recovery checks

**Status:** opt-in, unsigned, **local PostgreSQL audit observation** snapshot and comparison. This PR introduces no schema migration and **no runtime authorization** capability.

## Why a separate pin is required

PR #2448 preserves local audit observations and blocks conflicting inserts. A database administrator or restore process can nonetheless remove an entire packet and its cases, restore an older database backup, or edit a stored JSON record. Uniqueness constraints do not independently detect those changes.

This change captures an enumerated, bounded registry inventory and asks an operator to preserve the SHA-256 of the **complete checkpoint document** in a separately access-controlled place outside this database and outside the checkpoint JSON itself.

**The repository does not automatically transmit, securely anchor, sign, timestamp, or publish anything.** Without an independently preserved reference and digest, it cannot detect a coherent rollback that replaces both the database and local checkpoint.

## Operator flow (isolated trusted environment)

Configure the existing `VERITAS_DATABASE_URL` and apply the existing Alembic migration 0012. Capture a checkpoint after local archive ingest:

```sh
python -m scripts.validation.audit_registry_checkpoint_cli_v0_1 capture \
  --output ./audit-registry-baseline-v0_1.json
```

The command creates a new file (0600 permissions, exclusive creation, no overwrite) and prints `canonical_pinned_sha256`. **Keep this 64-hex hash independently** (for example, a human-approved, separately permissioned evidence register). A copy of the JSON file and its hash in the same restorable database volume is **not** an independent anchor.

After a subsequent ingest, restart or database restore, check against the baseline you preserved:

```sh
python -m scripts.validation.audit_registry_checkpoint_cli_v0_1 verify \
  --reference ./audit-registry-baseline-v0_1.json \
  --pinned-sha256 YOUR_INDEPENDENTLY_RETAINED_64_HEX_SHA256
```

The reference file itself is not trusted: the operator supplies the digest that was saved independently **before** the potentially destructive event. The tool validates the entire reference checkpoint against that digest. Neither that digest nor the reference is implicitly read from the database.

## Exact status contract

| Status | Meaning |
| --- | --- |
| `SNAPSHOT_READY_UNAUTHENTICATED` | A complete **bounded current DB inventory** was read in one snapshot; no external authority claimed |
| `HISTORY_UNCHANGED_UNAUTHENTICATED` | The pinned packet commitments still match and no extra packet exists **within the current observed registry** |
| `HISTORY_EXTENDED_UNAUTHENTICATED` | Every pinned packet commitment still matches; additional recorded packets exist |
| `HISTORY_DIVERGED` | A pinned packet is missing, or its header / case binding / record hashes differ; investigate recovery or privileged mutation |
| `REFERENCE_ANCHOR_MISMATCH` | Supplied reference does not match the separately pinned SHA-256 |
| `ANCHOR_REQUIRED` | No valid independent 64-character lowercase SHA-256 supplied |
| `REFERENCE_INVALID` | Malformed or self-inconsistent reference, including fabricated elevated trust fields |
| `INCOMPLETE` | Invalid local records, broken case counts, oversized registry, orphaned rows, etc. The scan **must not** silently truncate |
| `REGISTRY_UNAVAILABLE` | Database access or transaction failed; this is not a clean history pass |

The CLI exits with 0 only for `HISTORY_UNCHANGED_UNAUTHENTICATED` and `HISTORY_EXTENDED_UNAUTHENTICATED`; other verification statuses exit with 2. An extension does not automatically establish that every expected new packet was ingested; the system cannot independently enumerate intended input sets.

## How the checkpoint is built

- The scanner reads the entire local inventory using PostgreSQL **READ ONLY, REPEATABLE READ**, preventing torn snapshots when concurrent archive writes occur.
- Sorted packet headers include ID, local profile hash, self-declared repository key, source commit, snapshot digest and case count. Sorted case commitments include case ID and v0.1 record hash; the scanner also verifies every JSON record's existing schema/digest against the database columns and header.
- It computes a per-packet commitment, then a deterministic snapshot root over the ordered list and counts, and finally the canonical SHA-256 of the entire checkpoint document.
- The stored database JSON is capped at a modest size per case. The implementation returns `INCOMPLETE` if the registry exceeds **64 packets or 1,024 total cases**, if a packet/case count is inconsistent, or if a stored record is malformed. There is **no pagination or partial-success fallthrough** in this v0.1 implementation. A larger environment needs an independently reviewed scalable checkpoint scheme.
- Empty registries deliberately cannot produce a trusted-looking baseline.

## Tests and non-claims

The dedicated real PostgreSQL CI creates synthetic locally verified packets, captures a checkpoint, and verifies that exact retry and pool restart preserve the baseline, new ingest extends it, privileged deletion causes `HISTORY_DIVERGED`, modified case JSON causes `INCOMPLETE`, anchor substitution is rejected, and storage outage is not mistaken for success. Additional offline negative tests exercise forged authority fields, wrong counts, duplicate packets, malformed hashes and missing pinned values.

These are **synthetic tests** in a controlled CI container, not a physical disaster-recovery drill with independent storage accounts. Repairing synthetic rows after a test is not cryptographic proof of continuous retention.

This does **not** authenticate GitHub ownership, issuer signatures, the provenance of a submitted audit profile, trusted time, external effects, database administrators, backup retention, WORM custody, or that all expected historical packets have been seen. Checkpoint hashes are **not signatures**. The independent anchor's trust and retention are external operational prerequisites, not created by this tool.

The check is retrospective. No Bind Authorization, policy decision, single-use consumption, credential resolution or runtime execution boundary is altered.

## Merge gate

Keep PR #2449 as a **Draft** until final-head dedicated real PostgreSQL tests, negative test cases, broad CI, CodeQL, Security Gates and review of the external-pin trust assumption are complete. Existing audit archive semantics must remain unchanged.
