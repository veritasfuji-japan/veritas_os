# TASK-J3-03 — inert synthetic entry-gate state-machine prototype

**Status:** RESEARCH PROTOTYPE / NOT CONFORMANCE / NO REAL EFFECT  
**Predecessors:** merged PR #2454 (counterexample) and PR #2455 (feasibility + 38 proposed oracles).  
**Source:** `veritas_os/tests/research_j3_03_entry_gate.py`  
**Tests:** `veritas_os/tests/test_research_j3_03_entry_gate.py`

## What is implemented

A standalone test-only state machine named `SyntheticEntryGate` with a frozen attempt, two fixture-authenticated issuer evidence records, deterministic integer-millisecond UTC/monotonic readings, uncertainty bounds, a STOP epoch, owner-incarnation equality, one-shot attempt spending and an in-memory `E_SIM` receipt. `threading.Lock` orders synthetic clock mutations, STOP and the logical append.

No production policy module imports the model. It has no socket, TLS, subprocess, provider, real credential, disk write or external API.

### Tested logical predicates

- Two independent issuer validation ages must be in `[0,2000] ms`; expiry is strictly later than the conservative UTC upper bound.
- A check in the future, missing issuer, wrong target/digest/attempt/owner, unhealthy clock or STOP before entry denies.
- Synthetic STOP and `E_SIM` have an observable serialized order; STOP after entry cannot undo an already-recorded logical event.
- First attempted admission spends the local one-use right even on denial; concurrent attempts admit at most one.
- A simulated lost acknowledgement yields `UNKNOWN_NO_RETRY` and does not restore admission.
- A simulated interrupted claim yields `UNKNOWN_NO_RETRY`, but is **not** a real crash/restart test.

The test suite covers **selected** rows of the proposed 38-row matrix. It does not claim that all 38 rows are executed or that all assertions are independent cases.

## Critical limitation: not an atomic physical entry

`E_SIM` is an **abstract in-memory state-machine event**, not `writer.write`, kernel socket acceptance, packet transmission, receiver admission or external effect. The model's lock serializes synthetic clock advancement; it **cannot stop physical time from advancing while a thread is preempted inside the lock**. A preemption between the actual clock sample and an actual transport operation would recreate the original J3 gap.

Thus, the test proves only that the chosen **logical transition model** rejects the specified synthetic schedules. It does not prove that a Python lock, GIL, kernel call, native module, network stack or remote receiver can enforce the required entry-time guarantee. There is no durable one-use guarantee across restart, independent issuer signature verification, remote revocation visibility, or globally authenticated STOP/clock state.

`authenticated_in_fixture=True` is a synthetic test input, **not cryptographic authentication**. `payload_digest` is an opaque fixture identifier, not a computed cryptographic digest. Do not promote the model or its receipt into production code or conformance evidence.

## Run

    pytest -q veritas_os/tests/test_research_j3_03_entry_gate.py

CI outcomes and test counts must be reported separately from the intended assertions. No performance or network timing is measured.

## Next decision gates

1. Review which **actual** entry event Eric requires: E1 kernel acceptance, E2 physical send or E3 receiver admission. Do not conflate them.
2. Choose a candidate trust root and an independently observable linearization point; reject designs that only move check-before-write into a different process.
3. Define the remote revocation visibility model, STOP effective ordering, clock uncertainty and owner-incarnation persistence.
4. Build a separate inert platform-pinned candidate with fault injection **inside** the final check-to-entry interval. A model-only pass is insufficient.
5. Retain Strict RC1/J3 **BLOCKED**, J5–J7 **OPEN**, BA6 **PENDING**. Do not change Broker Admission draft2 or claim Eric approval.

## Explicit exclusions

The 38-row oracle matrix includes real transport semantics, kernel/platform proof, authenticated issuer signatures, STOP delivery visibility, crash recovery, durable one-use consumption, and partial network writes. These remain **NOT SCORED** here. Do not convert their absence into a passing result.
