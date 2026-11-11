# TASK-J3-05 — Trusted Entry architecture decision record (ADR v0.1)

**Status:** PROPOSED RESEARCH DECISION / NOT AN IMPLEMENTATION / NOT STRICT RC1 CONFORMANCE  
**Date:** 2026-11-05  
**Source evidence:** merged PRs #2454, #2455, #2456, #2457; `strict_rc1_j3_02_trusted_transport_entry_feasibility_v0_1.md`, `strict_rc1_j3_02_oracle_matrix_v0_1.md`, `strict_rc1_j3_04_local_kernel_call_gap_v0_1.md`.  
**Contract:** Sanction × VERITAS Strict RC1 entry event and revocation semantics are **not jointly frozen**. This ADR is a VERITAS research recommendation, not Eric Lovold's approval.

## Decision in one paragraph

**Do not select a production Trusted Entry mechanism yet.** Pursue a **receiver-side E3 admission candidate first as a conditional, explicitly different contract**, because an isolated receiver can in principle put its own admission check and logical commit at one local decision boundary. In parallel, retain **kernel-owned E1 entry as a separate feasibility track** if the partner requires sender-side kernel acceptance. A standalone trusted broker, sidecar, pre-send recheck, process lock, or signed permission handed to an unguarded sender **does not close the J3-04 check-to-send gap**. Neither candidate is accepted as Strict RC1 without the event definition, trust root, STOP/revocation model, and independently reviewed evidence.

## 1. Grounded current architecture

- `veritas_os/policy/sandbox_bind_execution.py` checks authorization, native one-second local window, credential metadata, and performs a one-shot `take_material()` callback. Durable intent is marked `EFFECT_UNKNOWN` before possible external effect.
- `veritas_os/policy/sandbox_https_transport.py` obtains the material, builds the wire bytes, calls `writer.write(wire)`, then awaits `writer.drain()`. Neither the Python callback nor `writer.write` is an independently authenticated E1/E2/E3 admission point.
- PR #2454 demonstrates a deterministic synthetic post-check/pre-write clock advance; #2456 models an in-memory atomic logical `E_SIM`; #2457 demonstrates a real AF_UNIX local-call gap, STOP-after-`E_SIM`, and a physical >2000 ms pause. These are **negative evidence for a split gate/send architecture**, not proof of all kernel or receiver implementations.
- J3-02 proposes two issuer final-check ages `0 <= T_entry - T_check_i <= 2000 ms`, strict `T_entry < T_expiry_i`, owner/binding equality, one-use and STOP ordering. These are **research predicates awaiting joint contract confirmation**, distinct from the existing native one-second local budget.

## 2. Candidate comparison

| Candidate | Where checks occur | Claimed event | Possible benefit | Fundamental gap / missing evidence | Verdict |
| --- | --- | --- | --- | --- | --- |
| A. Python or sidecar pre-send check | Before separate sender write | E0 only | Small change | Arbitrary preemption after check; `write` may buffer | **REJECT** as E1/E2/E3 proof |
| B. Standalone Trusted Broker | Before broker-to-transport handoff | Broker logical admission | Can centralize dual-issuer policy, custody and one-use state | Broker approval to physical send remains split unless broker owns and proves actual entry | **INSUFFICIENT ALONE** |
| C. Kernel-owned admission gate | In reviewed, platform-pinned kernel/transport mechanism | E1, only if specifically instrumented | Could order authority, STOP and queue admission under one trust root | No current primitive, trusted time/issuer validation, queue linearization or durable consumption proof | **CONDITIONAL E1 RESEARCH** |
| D. Sender scheduling/deadline features | Queue/scheduling subsystem | May bound or schedule parts of E1/E2 | Could reduce delays | Scheduling policy does not by itself validate two issuers, STOP or one-use; queue acceptance is not transmission | **NOT A COMPLETE GATE** |
| E. Receiver-side admission gate | At receiver-owned authoritative accept/commit boundary | E3 | Could revalidate fresh evidence after arbitrary sender delay | Different event/clock/STOP jurisdiction; E3 cannot retroactively satisfy E1 or E2 | **PREFERRED ISOLATED PROTOTYPE, CONDITIONAL CONTRACT** |
| F. Broker Admission draft2 | Logical broker admission and separate later write | Logical admission only | Coherent weaker local-disable profile | Not equivalent to Strict RC1 physical entry | **SEPARATE PROFILE; UNCHANGED** |
| G. Bounded real-time sender | Verified WCET/scheduler/clock platform | E1/E2 only as formally defined | May prove finite delay under strict assumptions | Unbounded preemption assumption must be excluded and proved; no such evidence today | **CONDITIONAL PLATFORM RESEARCH** |

**No numerical ranking is assigned:** required contract semantics and trust-root feasibility are unknown. The preferred prototype is chosen for *research tractability*, not claimed compliance.

## 3. Receiver E3 reference architecture (candidate, NOT deployed)

1. Sender freezes canonical operation, target, exact bytes/hash, attempt ID, owner incarnation and issuer evidence. The sender's local permission is advisory to E3, not E3 authorization.
2. Receiver independently authenticates **both issuer** evidence, its binding to the exact operation and current policy, using keys and issuer provenance it trusts; fixture flags are never authentication.
3. Receiver obtains an independently trusted time interval `[L,U]` and checks each issuer's final-validation age with conservative bounds, expiry `U < expiry_i`, and local STOP/revocation state.
4. Receiver atomically orders **E3 admission**, durable one-use consumption, STOP epoch and the immutable operation under one reviewed transactional/linearizable trust boundary. An ordinary database transaction may establish a **logical local commit**, but not a global STOP/clock truth or a downstream external effect.
5. Receipt identifies **E3 only**, event ordering, source/runtime identity, trust roots, issuer evidence references, immutable digest, attempt, owner incarnation and clock uncertainty. Lost receipts retain `UNKNOWN_NO_RETRY` and require read-only reconciliation.
6. Actual downstream effect **E4** is separately governed and evidenced. Receiver admission does not prove effect, nor sender E1/E2 freshness.

**Critical remote limitation:** A receiver cannot claim that a Sanction or VERITAS revocation became globally effective unless the parties define synchronous validation, a shared linearizable revocation authority, or an explicit bounded/stale-knowledge contract. If the agreement requires instantaneous remote revocation visibility, an isolated receiver with cached state is insufficient.

## 4. Kernel E1 research track

Before writing a kernel or native component, demand a **named OS/kernel/build and precise E1 event**. Show a trusted gate in which time/STOP/issuer checks and the *actual queue admission* share an instrumented ordering point; do not infer atomicity from `send()` return, eBPF hook placement, socket options, mutexes, or a syscall wrapper. Demonstrate control of exact bytes, immutable destination, partial writes, queueing, kernel bypass paths, crash/restart one-use state and code identity. A kernel-side receipt cannot assert E2 transmission, E3 receiver admission, or E4 effect without independent evidence.

Kernel privileges and deployment complexity introduce additional trust assumptions; do not promote this track merely because it is closer to the socket.

## 5. Threat model and trust boundary

| Threat / failure | E3 candidate must establish | E1 candidate must establish |
| --- | --- | --- |
| Pause after sender's final check | Receiver rechecks at E3 | Kernel-owned gate checks at E1 |
| STOP before admission | Receiver-visible STOP total order at E3 | Kernel-visible STOP total order at E1 |
| Remote issuer revocation not delivered | Explicit visibility guarantee or `NOT_SCORED` | Same; kernel does not magically learn remote state |
| Clock rollback/uncertainty | Trusted interval and fail-closed behavior | Trusted kernel/platform clock and fail-closed behavior |
| Altered target/body/owner | Cryptographically authenticated binding at E3 | Immutable binding at E1 |
| 32 concurrent entries / replay | Durable one-use E3 admission | Durable one-use E1 admission |
| Crash/receipt loss | `UNKNOWN_NO_RETRY`, read-only reconcile | Same; prove kernel/user-state recovery |
| Receiver accepts but downstream effect fails | E4 stays separate/unknown | E3/E4 stay separate/unknown |
| Sender has multiple bypass paths | Receiver rejects unauthorized operation | All E1 submission paths mediated or explicitly excluded |

A process-local lock and an in-memory synthetic `E_SIM` receipt are insufficient for either trust root.

## 6. Conditional selection gates

- **G0 CONTRACT:** Eric and VERITAS agree whether the requirement applies to E1, E2, E3, or more than one event; distinguish STOP acknowledgement from effective STOP and local vs global revocation visibility.
- **G1 TRUST:** Name the authority for UTC interval, monotonic clock, both issuer keys, revocation/STOP order, owner identity, durable one-use state, executable provenance and receiver/kernel boundary.
- **G2 ATOMICITY:** Provide an implementation-specific linearization proof for checks, one-use consumption, STOP and selected event. Explicitly inject preemption *inside* the alleged last check-to-entry interval.
- **G3 ADVERSARIAL:** Execute all 38 J3-02 oracles, including T08/F09 (pause inside gate), X02 expiry equality, S03/S07/S08 revocation ordering, F01 concurrency, F04/F05/F11 crash/restart. Unexecuted cases stay `NOT_SCORED`.
- **G4 EVIDENCE:** Pin platform/kernel/runtime/build hashes, immutable bytes and signatures, clock uncertainty, event/STOP ordering, persistence, traces and independent replay.
- **G5 PARTNER REVIEW:** Obtain explicit written acceptance of event semantics and evidence before changing the J3 status.

## 7. Decision consequences

- Next research deliverable: an **inert receiver E3 candidate** with explicit authority/STOP/time dependencies, not an external provider integration. It must demonstrate *local* admission properties without claiming global freshness.
- Keep the E1 kernel track open but **do not implement kernel hooks yet** until the entry event and trust root are agreed.
- Do not modify production `sandbox_bind_execution.py`, `sandbox_https_transport.py`, Broker Admission draft2, or Strict RC1 normative language in this task.
- **Strict RC1/J3 = BLOCKED; J5–J7 = OPEN; BA6 = PENDING partner review.** No conformance, approval, actual transport entry, or external effect is claimed.
