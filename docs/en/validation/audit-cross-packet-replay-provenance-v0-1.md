# Cross-Packet Replay & Claimed Provenance Audit v0.1

**Status:** offline audit helper; **not** a runtime admission engine, persistent replay registry, custody authority, issuer authentication, effect proof or certification.

## Why this exists

Audit Evidence Profile v0.2 and Bridge v0.2 bind one **local case** to its operation, manifest and evidence. They cannot detect the same IDs being reused across independently supplied Audit Evidence Profile **packets**. This PR adds a read-only, deterministic verifier over an *explicit caller-supplied packet set*.

A local `PASS` means only that **this supplied set** has no detected cross-packet replay, contradiction or missing required claimed metadata under this profile contract. Historical packets omitted from the invocation are invisible. This is **detection within a set**, not prevention or atomic single-use consumption.

## Interface and inputs

```python
from pathlib import Path
from scripts.validation.cross_packet_replay_provenance import (
    verify_cross_packet_replay_provenance,
)

report = verify_cross_packet_replay_provenance(
    packet_root=Path("/safe/isolated/packets"),
    profile_paths=["packet-a/profile.json", "packet-b/profile.json"],
)
```

CLI:

```shell
python -m scripts.validation.cross_packet_replay_provenance \
  /safe/isolated/packets \
  packet-a/profile.json packet-b/profile.json
```

All listed paths are relative to one supplied root. Maximum 64 profiles per call, 16 MiB per file, 64 MiB cumulative evidence bytes per profile, and bounded case/evidence item counts. Profile and evidence files are read without following symbolic links through directory-relative descriptors on supported POSIX operating systems. Reading is bounded and metadata-checked before and after. The existing v0.2 profile schema and local hashing validator must pass. This PR adds a **backward-compatible optional evidence hash resolver** to the existing validator; the scanner always supplies its own descriptor-rooted resolver so a resolved profile-parent path cannot redirect evidence reads outside the selected packet root. The caller must provide a stable, isolated evidence directory; concurrent changes remain outside the atomicity guarantees.

Only **v0.2 profiles** are accepted. A legacy v0.1 packet cannot silently skip operation-level identity checks.

Each bound case must refer to a local canonical JSON `EvidenceChainManifest` file already included in the v0.2 evidence inventory. The evidence SHA-256, canonical manifest bytes, internal manifest hash, case-level `decision_id`, `intent_id`, `operation_id`, `manifest_id`, other declared receipt IDs and available hash fields are checked. This **does not invoke the live chain verifier** or establish actual effect/authority validity. When present, Manifest identity fields ending in `_id` must be nonempty strings, while all Manifest `*_hash` fields (including `manifest_hash`) must be exactly 64 lowercase hexadecimal SHA-256 characters. Optional identities and hashes may remain `null`; malformed values are rejected even if both the Manifest digest and Profile evidence hash have been recomputed.

## Declared provenance binding

The manifest `metadata` must contain these caller-declared values, each exactly matching its corresponding Audit Evidence Profile field:

| Manifest metadata | Profile field |
| --- | --- |
| `audit_packet_id` | `packet_id` |
| `source_repository` | `scope.repository` |
| `source_commit` | `scope.source_commit` |

Missing metadata yields `INCOMPLETE`; conflicting values yield `FAIL`. Matching values yield `CLAIMED_CONTEXT_MATCHES_LOCAL_MANIFEST` — **not** `ORIGIN_AUTHENTICATED`. A malicious actor controlling both the profile and manifest can create internally consistent but false claims. This PR adds **no** external trusted issuer key or signature, authenticated git provenance, independent reviewer or hardware attestation.

The report deliberately separates `local_manifest_binding` from `declared_provenance_binding`, and fixes `origin_authentication=NOT_PERFORMED` and `external_origin_authenticated=false`.

## Replay/concurrency checks

Across distinct supplied packet files:

- A repeated `packet_id` is flagged, regardless of file path.
- A repeated `(scope.repository, operation_id)` is flagged.
- A repeated `(scope.repository, manifest_id)` is flagged.
- A repeated manifest **canonical SHA-256** is flagged, including across repositories.
- Repeating a local profile path within the same request is an input failure.

Repository scoping uses case-insensitive names for repeated operation and manifest identifiers, avoiding trivial casing bypasses while allowing distinct repository namespaces. It avoids treating unrelated tenants' identical local operation identifiers as replay. The caller must still ensure repository names themselves are authoritative; this local check does not.

Status precedence: `FAIL` (invalid/malformed/contradictory) over `REPLAY_DETECTED` over `INCOMPLETE` over `PASS`. All findings are returned deterministically; an invalid packet is **not** skipped and then treated as a complete successful audit.

The report contains a canonical `snapshot_digest` over the accepted packet/link inventory. Optional `expected_snapshot_digest` compares against a digest supplied by the caller; a match is labeled `MATCHED_CALLER_SUPPLIED_DIGEST` and explicitly does **not** verify an independent external anchor. This digest is **not** a cryptographic audit log or an authenticated completeness promise.

## Limitations / future stages

1. **No persistent history:** a packet omitted from this invocation cannot trigger replay detection. See the negative/limitation test that deliberately demonstrates this blind spot.
2. **No atomic admission:** simultaneous independent invocations can each pass. Durable single-use consume and concurrency/rollback handling require a separately trusted stateful boundary.
3. **No authoritative provenance:** an attacker who can edit both the claimed profile and manifest can create matching identifiers/hashes; trust must be obtained from independent issuers/signatures, timestamping and retention architecture.
4. **No execution evidence assessment:** successful local equality is not proof that an AI agent was authorized, denied, committed, or prevented from causing a side effect.
5. **No transitive completeness:** the caller-provided packet list is not externally anchored, notarized, immutable or exhaustively enumerated.
6. **No production enforcement:** PR #2446 is additive and read-only; it changes no authority issuance, Bind/Custody, runtime effect boundary, signing, or benchmark scoring.

## Required CI and review gates

- Two distinct synthetic v0.2 packets pass with clearly labeled, unauthenticated provenance.
- Repeated packet, operation, manifest ID, and bytes across packets are rejected.
- Changed operation or decision IDs, forged/missing provenance metadata, contradictory declared effects, malformed manifest field types, tampered manifest bytes/hash, symlinked paths, invalid versions, oversized inputs, cumulative evidence-limit violations, and duplicate paths fail closed.
- Reports remain deterministic under input order changes.
- A caller-supplied digest mismatch is rejected; a matching digest never counts as external authentication.
- v0.1 and v0.2 Profile/Bridge regression tests remain green.
- **All final-head GitHub Actions runs and an explicit trust-boundary review must be complete before merging.**
