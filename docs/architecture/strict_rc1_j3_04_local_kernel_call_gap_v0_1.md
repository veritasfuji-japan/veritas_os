# TASK-J3-04 — Local kernel-call seam / STOP / physical-clock counterexamples

**Status:** RESEARCH ONLY — negative evidence for split gate/send architecture  
**Predecessors:** PR #2454 (post-check/pre-write fake-clock seam), PR #2455 (J3 feasibility + oracle matrix), PR #2456 (in-memory E_SIM logical gate).  
**Files:** `veritas_os/tests/research_j3_04_local_socket_seam.py` and `veritas_os/tests/test_research_j3_04_local_socket_seam.py`  
**No real provider, IP network, DNS, TLS, external effect, or production code change.**

## 1. Research question

Can the logical entry receipt from J3-03 prove that a subsequent physical transport operation is admitted before a 2000ms deadline or a STOP that takes effect after E_SIM?

**No, not for the split architecture exercised here.** J3-03's `E_SIM` and a later local `socket.send()` are different events. Arbitrary scheduling or STOP can occur between them. This is an architecture-specific counterexample, not a theorem that all kernel/receiver-based approaches fail.

## 2. Instrumented local-only experiment

The harness uses `socket.socketpair()` (AF_UNIX) with a tiny inert byte string. A worker calls J3-03's `attempt_entry()`, records `time.monotonic_ns()` immediately after returning, signals a test barrier, then waits on a threading event. The controller may trigger STOP, let physical time advance, or close the local peer. Only after the controller releases the barrier does the worker call `socket.send()`. The receiver verifies local bytes using `recv()`.

This is a real **local socket syscall** path on the CI host, but **not** a trusted E1 linearization-point instrument. The timestamps bracket the Python-level syscall invocation/return; they do not establish the instant of kernel internal acceptance. A successful return means the local call reported acceptance of the observed byte count, not E2 physical network transmission, E3 authenticated receiver admission, or E4 external effect.

The fixture's issuer timestamps and UTC/monotonic model are **synthetic**. `time.monotonic_ns()` separately measures actual elapsed time across the controlled pause. The source digest is an opaque fixture string and does not authenticate the sent bytes.

## 3. Planned/implemented tests and evidence limits

| Case | Schedule | Expected observable | Not proven |
| --- | --- | --- | --- |
| L01 | E_SIM then release and local send | Successful local syscall return and local recv | E1 precise acceptance point; E2–E4 |
| L02 | E_SIM, then STOP, then local send | Local bytes still accepted after effective synthetic STOP | Remote STOP semantics or real trusted STOP |
| L03 | E_SIM, physically pause >2000ms, then local send | Actual monotonic gap >2000ms; stale split gate still sends | True issuer timestamps or production time trust |
| L04 | STOP before E_SIM | Logical denial; no local bytes | Kernel-enforced admission |
| L05 | E_SIM then pause timeout | No local send; one-use attempt stays spent | Crash persistence |
| L06 | E_SIM then close local peer | Send fails, no re-arm in same in-memory model | Durable UNKNOWN/reconciliation |
| L07 | E_SIM then substitute inert payload bytes | Opaque receipt digest does not bind physical sent bytes | Cryptographic digest verification |

These are **seven test functions**, not seven independent proof obligations discharged. CI pass/fail must be verified after PR creation. The physical pause test deliberately waits slightly more than two seconds; it is not a performance benchmark.

## 4. Findings and interpretation

- **STOP-before-E_SIM** denies as J3-03 specifies; **STOP-after-E_SIM-before-send** cannot retract the already-issued logical receipt or prevent a subsequent unguarded local syscall.
- A physically observed >2000ms gap can occur between E_SIM and the local send call, even though the model's fake clock is unchanged. This refutes treating E_SIM as a timestamp for the later local send.
- An unbound opaque payload digest cannot prove which bytes a later sender actually submitted.
- Local socket call return and receiver byte observation are distinct observations; neither establishes a cryptographically authenticated external effect.
- The test does not imply that a real receiver would accept the operation; there is no receiver authority check here.

## 5. Remaining proof obligations

1. **Contract:** Obtain explicit agreement on the selected event E1/E2/E3 and where the two-issuer age and expiry predicates must hold.
2. **Atomicity:** Choose a trusted component that binds actual time, STOP, issuer evidence, immutable bytes and one-use admission to the **same** selected entry event; otherwise preserve BLOCKED.
3. **Time trust:** Define UTC uncertainty, monotonic calibration, revocation propagation and threshold equality under platform-pinned assumptions.
4. **Durability:** Verify owner incarnation and single-use state across crashes/restarts, with unambiguous no-retry handling for unknown outcomes.
5. **Independent evidence:** Pin source hash, OS/kernel, Python, clock details, trace/receipt and independent replay; do not treat Python bracketing timestamps as kernel proof.
6. **Adversarial scope:** Exercise the full 38-row J3-02 oracle matrix in a separately reviewed candidate; this PR covers only selected counterexamples.

## 6. Decision

**Strict RC1/J3 = BLOCKED.** J5–J7 OPEN, BA6 PENDING partner review. Broker Admission draft2 unchanged. No normative Sanction approval, no transport conformance claim, no external effect.

This is an isolated negative-evidence experiment, not a deployable Trusted Entry Gate.
