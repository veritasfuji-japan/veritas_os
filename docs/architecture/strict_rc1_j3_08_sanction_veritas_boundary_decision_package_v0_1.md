# TASK-J3-08 — Sanction × VERITAS Strict RC1 boundary decision package (v0.1)

**Status: PROPOSED FOR JOINT REVIEW — NOT SENT / NOT AGREED / NOT NORMATIVE**  
**Prepared:** 2026-11-05  
**Scope:** decide the meaning of Trusted Entry and STOP/revocation before selecting a production mechanism.  
**Sources:** merged J3 research #2454–#2460, especially J3-05 ADR/partner questions, J3-06 SQLite E3-model, and J3-07 conditional temporal envelope.  
**No assertion is made about Sanction's current implementation, commitments, or Eric Lovold's position.**

## 1. Purpose and proposed review outcome

This packet requests **three independent decisions**, not an approval of VERITAS's E3 research:

- **D1 / Q01 — What exact event is constrained?** E1 kernel queue admission, E2 actual network transmission, E3 authenticated receiver admission, or a specified combination. An E3 result is not E1/E2 evidence.
- **D2 / Q04 — What makes STOP effective?** Specify the authority, the linearization point, the scope (operation/attempt/owner/issuer), and the meaning of acknowledgement. Receipt of a STOP request, local database commit, and globally effective STOP are different events.
- **D3 / Q05 — When must a remote revocation be visible?** Instantaneous/global, synchronous authoritative validation at entry, bounded-staleness with a specified failure policy, or another explicitly defined rule. A receiver's cached flag does not prove global visibility.

**Requested response:** for each decision, record a selected option or `UNRESOLVED`, a precise normative sentence, the trust/ordering authority, evidence required to test it, and any open objections. Silence, a meeting, or acceptance of this packet is **not** acceptance of a contract.

## 2. Event vocabulary — keep distinct

| Event | Definition for discussion | Evidence that could support it | What it cannot establish alone |
| --- | --- | --- | --- |
| E0 | application-level precheck or handoff | policy logs and code path | kernel admission, transmission, receiver acceptance or effect |
| E1 | entry into a specifically identified kernel-owned queue/admission point | platform-pinned, independently instrumented kernel boundary | E2, E3, E4 |
| E2 | actual transmission of the specified bytes over the relevant network boundary | event-specific transport instrumentation and binding | E3 or E4 |
| E3 | receiver-owned authoritative admission of the exact operation | authenticated receiver and reviewed admission linearization proof | E1/E2 freshness or E4 |
| E4 | external operation/effect | independent provider-side effect evidence | prior entry-event freshness by itself |

A successful `socket.send`, `writer.write`, `drain`, logical broker approval, or SQLite commit **must not be silently re-labelled** as E1/E2/E3. If multiple events are required, state the predicate and trust root **for each**.

## 3. Decision worksheet — questions for Eric and VERITAS

### D1 / Q01: exact entry event

**Select one or more:** `E1`, `E2`, `E3`, `OTHER_DEFINED`, `UNRESOLVED`. If multiple, specify whether all are mandatory and which event the proposed 2000ms freshness and strict expiry predicates apply to.

Please specify: immutable payload/target/owner binding; event observation/receipt source; where issuer verification runs; whether the event may be retried; what is excluded (e.g., queue acceptance is not transmission).

**Conditional architecture implications:**
- If **E1** is required, the current inert E3-model does not satisfy it. Investigate a named, pinned kernel/transport gate only after its trust/linearization point is defined.
- If **E2** is required, neither E1 nor E3 can substitute for independently evidenced transmission. Define partial sends, retransmission and transport buffering.
- If **E3** is required, receiver-side research can continue, but J3-06 is *not* a real authenticated receiver and J3-07 does *not* certify a bounded delay.
- If **E1 and E3** (or more) are required, define separate checks, event ordering and cross-boundary failure semantics.

### D2 / Q04: STOP-effective point

**Select a precise authority/order:** `SAME_TRUST_ROOT_AT_ENTRY`, `REMOTE_AUTHORITY_SYNCHRONIZED`, `OTHER_DEFINED`, `UNRESOLVED`. The labels are prompts, not proposed contractual defaults.

Please distinguish these timestamps/events: STOP requested, STOP accepted/acknowledged, STOP effective, admission started, admission linearized, external effect occurred. State whether STOP effective before E **must** deny E, and whether STOP effective after E can revoke an already admitted operation or only future entries. State how concurrent STOP/admission races are ordered and what evidence a third party can replay.

**Mandatory failure example:** STOP request arrives while the entry gate holds a local transaction lock. If admission commits first, is STOP *not yet effective*, or is a separate upstream authority already effective? A local SQLite lock does not decide the answer for a remote authority.

### D3 / Q05: remote revocation visibility

**Select:** `SYNCHRONOUS_AUTHORITATIVE`, `BOUNDED_STALENESS`, `INSTANTANEOUS_GLOBAL`, `OTHER_DEFINED`, `UNRESOLVED`. This is a question about the contract, not an implementation recommendation.

Please specify: issuer of revocation, authoritative publication/commit point, visibility requirement at selected E, maximum permitted propagation delay (if any), partition/timeout policy, clock assumptions, recovery/restart behavior and proof of freshness.

- `SYNCHRONOUS_AUTHORITATIVE`: define a linearizable read/validation, the authorization snapshot, and the race between validation and E.
- `BOUNDED_STALENESS`: define the bound, whether an already effective revocation can still be accepted within it, and explicit fail-closed rules when the bound cannot be established.
- `INSTANTANEOUS_GLOBAL`: identify the physical/distributed trust mechanism and its failure model; **do not assume this is implementable** under partitions.
- `UNRESOLVED`: no conformance claim; research may continue only under separate labelled assumptions.

## 4. Secondary decisions required before freezing Strict RC1

| Existing question | Joint decision still needed | Current status |
| --- | --- | --- |
| Q02 | Is each issuer's final-check age `0 ≤ T_E − T_check_i ≤ 2000ms` at selected E, and how is measurement uncertainty handled? | PROPOSED, not frozen |
| Q03 | Is `T_E < expiry_i` strict for each issuer, with equality denied? | PROPOSED, not frozen |
| Q06 | Independent issuer roots, revocation root, trusted UTC/monotonic time and uncertainty, owner identity, code provenance, durable one-use state | OPEN |
| Q07 | Lost receipt, partial send, crash/restart and `UNKNOWN_NO_RETRY`/read-only reconciliation | PROPOSED, not frozen |
| Q08 | May E3 be evaluated as a separate research profile without being represented as E1 conformance? | PROPOSED |

The proposed 2000ms predicates are research oracles; the separate existing native 1-second local budget is not replaced by agreement on these questions.

## 5. Evidence already available versus missing

| Research evidence | Demonstrated in VERITAS | Does not prove |
| --- | --- | --- |
| #2454 / J3-01 | post-check/pre-write timing counterexample | selected physical entry |
| #2455 / J3-02 | E0–E4 taxonomy and proposed 38 adversarial oracles | partner-approved contract or executed full matrix |
| #2456 / J3-03 | synthetic logical E_SIM and one-use fixture | kernel/receiver entry |
| #2457 / J3-04 | AF_UNIX local-call gap, physical pause | all possible kernel mechanisms |
| #2458 / J3-05 | conditional E3 research recommendation; E1 retained as alternative | partner selection or production gate |
| #2459 / J3-06 | local SQLite receiver-model STOP/one-use ordering; >2000ms in-transaction time-gap counterexample | real E3, globally effective STOP, trusted time |
| #2460 / J3-07 | conditional arithmetic `[L,U]` + certified `B` envelope and negative proof obligations | certification of `B`, real time root, E1/E2/E3/E4 |

**Missing before conformance:** written event/STOP/revocation contract; actual selected-event instrumentation; independent issuer/key and clock roots; verified worst-case bound or atomic trusted entry primitive; global STOP/revocation model; durable one-use and crash semantics; full 38-oracle evidence and independent replay.

## 6. Decision outcomes and next engineering branches

| Joint result | Authorized next research step | Must not claim |
| --- | --- | --- |
| D1=E1 with D2/D3 specified | named kernel/platform feasibility plan, event instrumentation and trust-root threat model | E1 already proved |
| D1=E2 with D2/D3 specified | transmission event definition, buffering/partial-send/STOP race study | `send()` return proves E2 |
| D1=E3 with D2/D3 specified | independently authenticated receiver E3 feasibility plan with STOP/one-use/clock evidence | SQLite E3-model is real E3 |
| Multiple entry events | separate per-event proof obligations and cross-event failure model | one receipt proves all events |
| Any of D1/D2/D3 unresolved | preserve separate research profiles; ask targeted follow-up | Strict RC1 acceptance or changed normative status |

**Change control:** record both parties' explicit agreement and source references in a separate decision record. Do not edit the normative contract, production dispatch path or status based solely on this proposed packet. No email or external message is sent by this PR.

## 7. Publication and communication boundary

This repository contains only technical questions, evidence requirements and proposed decision-record structure. Any partner-directed email or message is prepared, reviewed and sent separately outside this public repository. Publication of this packet does not imply Sanction approval or joint agreement.

**Strict RC1/J3 BLOCKED; J5–J7 OPEN; BA6 PENDING partner review.** No external effect, partner acceptance or production conformance is claimed.
