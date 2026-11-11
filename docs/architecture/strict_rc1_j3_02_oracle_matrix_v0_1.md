# TASK-J3-02 — adversarial timing / authority oracle matrix (v0.1)

**Status:** PROPOSED / NOT EXECUTED / NOT CONFORMANCE TESTS  
**Baseline:** main after PR #2454 (`6f4efbda5dd4c4e84adb4a96afeedb4f7b3f7bdd`)  
**Purpose:** define observable outcomes before choosing a trusted transport-entry primitive.  
**Precondition:** all cases use synthetic frozen payloads, fake credentials, inert transports and deterministic event ordering. A future candidate must define the exact entry linearization point `E` before running them.

## Oracle language

- `DENY_NO_ENTRY`: no event `E`; no external effect.
- `ENTRY_COMMITTED_ONCE`: exactly one authenticated `E` with a single-use receipt; **not** proof of effect.
- `UNKNOWN_NO_RETRY`: an ambiguous attempt is retained, and the same operation is never dispatched again.
- `NOT_SCORED`: cannot decide without the stated trust/ordering definition.
- `STOP_PRECEDES_E`: the effective disable linearizes before `E`.
- `E_PRECEDES_STOP`: the entry linearizes before disable; no retrospective rollback claim.

The proposed two-issuer age bound is `[0,2000] ms`; expiry requires strict `T_entry < T_expiry`. The native one-second local budget is separate. Unless specified, assume exact trusted timestamps for boundary oracles; clock-uncertainty cases override that assumption.

## Group T — final-validation age

| ID | Event schedule | Expected oracle |
| --- | --- | --- |
| T01 | Both final validations 0 ms before `E`, expiry safely later | `ENTRY_COMMITTED_ONCE` |
| T02 | Both 1999 ms before `E`, expiry later | `ENTRY_COMMITTED_ONCE` |
| T03 | Both exactly 2000 ms before `E`, expiry later | `ENTRY_COMMITTED_ONCE` under exact-time contract |
| T04 | Sanction 2001 ms old; VERITAS 0 ms old | `DENY_NO_ENTRY` |
| T05 | VERITAS 2001 ms old; Sanction 0 ms old | `DENY_NO_ENTRY` |
| T06 | One issuer's check timestamp is in the future relative to `E` | `DENY_NO_ENTRY` |
| T07 | Python check succeeds; process paused 2001 ms before candidate gate | `DENY_NO_ENTRY` |
| T08 | Candidate gate checks, is preempted 2001 ms, then accepts E without revalidation | **FAIL design**; counterexample to proposed gate |
| T09 | Missing one issuer's authenticated final-validation evidence | `DENY_NO_ENTRY` |
| T10 | Issuer evidence swapped across attempts or targets | `DENY_NO_ENTRY` |

## Group X — expiry and clock

| ID | Event schedule | Expected oracle |
| --- | --- | --- |
| X01 | `E = T_expiry - 1 ms` for both issuers | `ENTRY_COMMITTED_ONCE`, if all other predicates hold |
| X02 | `E = T_expiry` for either issuer | `DENY_NO_ENTRY` |
| X03 | `E = T_expiry + 1 ms` for either issuer | `DENY_NO_ENTRY` |
| X04 | UTC interval upper bound reaches expiry, point estimate before expiry | `DENY_NO_ENTRY` |
| X05 | Clock health missing, uncertainty unbounded, or clock rollback | `DENY_NO_ENTRY` |
| X06 | Wall clock and monotonic age disagree | `DENY_NO_ENTRY` until specified reconciliation rule |
| X07 | Unknown timestamp resolution / ambiguous threshold equality | `DENY_NO_ENTRY` or `NOT_SCORED` until clock model agreed |
| X08 | A late physical transmission follows an E1 admission within deadline | **E1-only** claim; E2/E3/E4 remain `NOT_SCORED` |

## Group S — STOP, revocation and ownership

| ID | Event schedule | Expected oracle |
| --- | --- | --- |
| S01 | STOP linearizes before E | `DENY_NO_ENTRY` |
| S02 | E linearizes before STOP | `ENTRY_COMMITTED_ONCE` only if all other conditions hold; no claim of undoing bytes |
| S03 | STOP and E race without auditable total order | `DENY_NO_ENTRY` or `NOT_SCORED`; never claim success |
| S04 | STOP effective before last check; stale owner view | `DENY_NO_ENTRY` if contract requires globally current STOP; otherwise explicitly mark visibility gap |
| S05 | Original owner incarnation replaced after restart | `DENY_NO_ENTRY` |
| S06 | Different executor attempts same frozen dispatch | Exactly one E at most; others `DENY_NO_ENTRY` |
| S07 | One issuer revokes remotely before E but local gate has not learned it | `NOT_SCORED` until revocation visibility semantics are fixed; cannot claim global validity |
| S08 | STOP acknowledged but local gate has not applied it | `NOT_SCORED` until acknowledgment vs effective disable are distinguished |

## Group F — faults, replay and evidence

| ID | Event schedule | Expected oracle |
| --- | --- | --- |
| F01 | 32 concurrent contenders for same one-use right | At most one `ENTRY_COMMITTED_ONCE`; all others denied |
| F02 | Gate commits E, response/receipt lost | `UNKNOWN_NO_RETRY`; independent read-only reconciliation may classify later |
| F03 | Gate fails before E with authoritative proof of no entry | `DENY_NO_ENTRY`, but spent attempt must not silently re-arm |
| F04 | Process crash after one-use claim, before E; no proof of E | `UNKNOWN_NO_RETRY` unless a trusted no-entry proof supports narrower classification |
| F05 | Crash after E, before local observation | `UNKNOWN_NO_RETRY`; do not infer effect |
| F06 | Replayed entry receipt, copied permit or altered idempotency key | `DENY_NO_ENTRY` for new entry |
| F07 | Partial write / queue acceptance followed by network failure | E1 may be recorded, external effect `UNKNOWN`; no resend |
| F08 | Candidate receipt omits entry point, time trust, source hash or owner incarnation | `NOT_SCORED` for conformance; fail closed operationally |
| F09 | Candidate gate internally checks then pauses before separate write | **FAIL design**; no Strict RC1 proof |
| F10 | Gate runs on unreviewed kernel/runtime or mismatched implementation digest | `DENY_NO_ENTRY` / `NOT_SCORED` |
| F11 | Same attempt re-enters after restart/recovery | `DENY_NO_ENTRY` |
| F12 | Receiver reports 200/201 after a late sender-side write | No authority upgrade; entry-time violation is not repaired by acknowledgment |

## Minimum evidence package for any future implementation

1. Frozen contract version and chosen E0/E1/E2/E3 event definition.
2. Source and executable hashes, OS/kernel/compiler/runtime versions, environment manifest.
3. Two issuer evidence signatures, timestamps, expiry and canonical target/attempt binding.
4. Clock-trust and uncertainty proof; monotonic trace and ordering of STOP vs E.
5. Durable one-use/owner state before and after, crash/restart recovery records.
6. Inert deterministic trace for every oracle, including failure injection placement.
7. Independent reviewer replay, false-positive/negative analysis and unresolved limitations.

**No case in this document is claimed to have been executed.** Existing PR #2454's four passing synthetic tests are separate, and do not satisfy this matrix. Strict RC1/J3 remains **BLOCKED**.
