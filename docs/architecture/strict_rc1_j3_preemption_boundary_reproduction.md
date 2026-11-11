# Strict RC1 / J3 — post-check/pre-write timing counterexample

Status: **research reproduction, NOT conformance evidence**  
Scope: isolated synthetic Python test, no DNS, real TLS, external provider or real effect  
Source baseline: [`6c2f5ef264ee1d0de4970228a03653262e6c9663`](https://github.com/veritasfuji-japan/veritas_os/commit/6c2f5ef264ee1d0de4970228a03653262e6c9663)

## Research question

Can a final successful native send-window check be followed by a clock advance
before the concrete HTTPS transport invokes `writer.write(wire)`, without
another check preventing the write?

The native path invokes `take_material()` at
`veritas_os/policy/sandbox_https_transport.py:123` and `writer.write(wire)`
at line 128. The callback's clock checks live in
`veritas_os/policy/sandbox_bind_execution.py:203-214,236-244`.
There is no additional `trusted_clock()` call between the callback return and
the writer invocation in this path.

The existing native executor-local gate requires wall and monotonic elapsed
time each to be at most one second from `started`, in addition to
authorization validity and credential metadata checks. This is **not**
equivalent to the joint Strict RC1 two-second final-validation-to-transport-entry
requirement.

## Reproduction design

`veritas_os/tests/test_strict_rc1_j3_preemption_boundary.py` uses existing
sandbox test fixtures and the **real production Python transport code** with a
fake `asyncio.open_connection`, in-memory effect state, and synthetic bearer
material. It patches the synthetic material's `get_secret_value()` only after
the fake connection is established. That method is called **after**
`take_material()` has completed and **before** `writer.write()`.

At this point the test advances the injected trusted clock by one of:
1000, 1001, 2000, or 2001 ms. It records whether the fake writer was invoked
and confirms that the durable state stays `EFFECT_UNKNOWN` and the original
attempt cannot be retried.

The test is deliberately written to **pass when the present limitation is
observed**; it does not use xfail, which could be confused with a successful
safety property. A future real fix must update this regression evidence and
add a separate positive safety test.

## Interpretations and limits

- 1000/1001 ms are the executor-local one-second boundary; 2000/2001 ms
  are the joint Strict RC1 freshness boundary. The experiment does not
  independently establish issuer validation timestamps.
- Advancing a synthetic clock inside a synchronous method models a gap;
  it does **not** reproduce a true OS preemption or establish a kernel
  linearization point.
- `writer.write()` may buffer bytes. It is an application-side invocation,
  **not proof** of kernel transport entry, peer receipt or external effect.
- No owner-disable race is claimed by this test. STOP ordering, trust root,
  bounded clock uncertainty, true transport entry and exact F10/F11
  boundaries remain separate work.
- A user-space mutex or another Python check before `writer.write()`
  does not alone prove immunity to arbitrary preemption after that check.
- This test is not a substitute for Eric's BA6 source-pinned inventory,
  the Broker Admission draft2 oracle suite, or Strict RC1 conformance.

## Run

```bash
pytest -q veritas_os/tests/test_strict_rc1_j3_preemption_boundary.py
```

Expected on the baseline: four passing observations, with one fake write per
case and `EFFECT_UNKNOWN` retained. This is an **expected observation**,
not a result claimed until CI or local execution confirms it.

## Next evidence gates

1. Verify this test on CI and preserve run ID / commit SHA.
2. Establish a precise definition of actual transport entry with Eric.
3. Investigate whether a trusted native mechanism can atomically enforce
   owner eligibility, both issuer deadlines, and one-use transport entry
   under arbitrary scheduling interruption.
4. Keep Strict RC1/J3 **BLOCKED** until such a mechanism and its adversarial
   timing tests are demonstrated. Do not relabel broker admission as RC1.
