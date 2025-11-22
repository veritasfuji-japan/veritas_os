# VERITAS OS — Proto-AGI Decision OS / Public API

This repository contains **VERITAS OS**, a Proto-AGI framework that wraps an LLM
(e.g. OpenAI API) as a:

> **“Safe, consistent, and auditable decision-making OS”**

instead of “just a chatbot”.

VERITAS OS treats the LLM as a low-level reasoning engine and builds on top of it
a full **Decision OS / Agent OS** with safety, memory, value functions, world
state, and trust-logs.

---

## 🔥 TL;DR
![IMG_1157](https://github.com/user-attachments/assets/c76cef57-485e-40b3-917f-62dc2a7e535b)


- **VERITAS OS = OS-layer that wraps an LLM as a Proto-AGI Decision OS**
- A single call to **`/v1/decide`** executes:

  `Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog`

- Exposed as a **local FastAPI (uvicorn) service**, callable from **OpenAPI 3.1 +
  Swagger Editor/Studio**
- Includes **MemoryOS / WorldModel / ValueCore / FUJI Gate / Doctor Dashboard**
  as an integrated stack
- Goal: an **experimental backbone for using LLMs as safe, repeatable, and
  auditable AGI skeletons**

Conceptually:

- **LLM ≈ CPU**
- **VERITAS OS ≈ Decision / Agent OS that runs on top of it**

---

## 🎯 1. What can it do?

### 1.1 `/v1/decide` — Full decision loop
![IMG_1159](https://github.com/user-attachments/assets/f072aef0-beb1-4b26-9bfc-3e5b4bda21a3)

`POST /v1/decide` always returns a structured JSON payload containing:

- `chosen`  
  The selected action (with `action`, `rationale`, `uncertainty`).
- `alternatives[]`  
  Other viable options that were considered.
- `evidence[]`  
  Evidence items referenced during the decision.
- `critique[]`  
  Self-critique of the candidate plan.
- `debate[]`  
  Multi-view internal debate (e.g. pro/contra/third view).
- `telos_score`  
  Alignment with the current value function.
- `fuji`  
  Safety/ethics decision (`allow | modify | block | abstain`).
- `trust_log`  
  Hash-chained log entries (`sha256_prev`) for auditability.

Because the **decision process** (not only the answer) is serialized,
VERITAS is intended to be useful for:

- AGI research
- AI safety / alignment experiments
- Auditable decision-making systems

---

### 1.2 Other APIs

All endpoints require an **`X-API-Key`** header.

| Method | Path                             | Description                                       |
|--------|----------------------------------|---------------------------------------------------|
| GET    | `/health`                        | Health check for the server                       |
| POST   | `/v1/decide`                     | Full decision loop                                |
| POST   | `/v1/fuji/validate`             | Safety / ethics validation for a single action    |
| POST   | `/v1/memory/put`                | Store a key/value pair in persistent memory       |
| GET    | `/v1/memory/get`                | Retrieve a value from persistent memory           |
| GET    | `/v1/logs/trust/{request_id}`   | Retrieve immutable hash-chained trust log entries |

---

## 🧠 2. Context schema (for AGI-style tasks)

AGI-like **meta-decision** tasks are expressed via a `Context` object
(OpenAPI 3.1 excerpt):

```yaml
Context:
  type: object
  required: [user_id, query]
  properties:
    user_id:      { type: string }
    session_id:   { type: string }
    query:        { type: string, description: "User request / problem statement" }
    goals:        { type: array,  items: { type: string } }
    constraints:  { type: array,  items: { type: string } }
    time_horizon: { type: string, enum: ["short", "mid", "long"] }
    preferences:  { type: object }
    tools_allowed:
      type: array
      items: { type: string }
    telos_weights:
      type: object
      properties:
        W_Transcendence: { type: number }
        W_Struggle:      { type: number }
    affect_hint:
      type: string
      enum: ["calm", "focused", "empathetic", "concise"]

With this schema you can ask VERITAS to decide, for example:
	•	The optimal next steps of an AGI research plan
	•	The next move in a self-improvement loop
	•	An experimental plan that respects strict safety boundaries

by sending such a context directly to /v1/decide, and delegating
the top-level decision to the OS.

⸻

🏗 3. Repository layout (veritas_clean_test2)

The top-level layout (simplified, based on the current working tree):

veritas_clean_test2/
├── chainlit_app.py
├── chainlit.md
├── data/
│   └── value_stats.json
├── docs/
│   ├── agi_self_hosting.md
│   ├── bench_summary.md
│   ├── fail_safe.md
│   ├── fuji_gate_safety.md
│   ├── metrics.md
│   ├── module_responsibilities.md
│   ├── self_improvement_commands.md
│   ├── worldmodelstep1.md
│   └── ...
├── veritas_os/
│   ├── api/
│   ├── core/
│   ├── scripts/
│   ├── templates/
│   ├── tools/
│   ├── README.md
│   ├── README_ENGLISH.md
│   └── requirements.txt
├── reports/
├── backups/
├── datasets/
└── .gitignore

The interesting part for researchers is mainly veritas_os/,
especially core/ and api/.

⸻

🧩 4. veritas_os/core/ module responsibilities
![IMG_1160](https://github.com/user-attachments/assets/cf029b29-1fbe-4264-9223-4c6a29ed22eb)

This directory is the heart of VERITAS OS.
Below is a map of the main *.py modules so that researchers/engineers
can navigate the codebase quickly.

4.1 Core OS layer
	•	kernel.py
Global orchestrator of VERITAS.
Called from /v1/decide and runs:
Planner → Evidence → Critique → Debate → FUJI → World/Memory update
then assembles the final DecideResult.
	•	pipeline.py
Defines the stage structure and execution flow of the decision
process:
which OS component runs when, and which metrics are collected.
	•	planner.py (PlannerOS)
Builds multi-step task plans from query / goals / constraints.
Produces not only “the next move”, but a steps[] plan for
short-/mid-term horizons.
	•	reason.py (ReasonOS)
Manages chain-of-thought style reasoning with the LLM.
Generates internal reasoning text informed by evidence & critique, and
backs DecideResponse.trace / rationale.
	•	strategy.py
High-level strategy policy:
exploration vs exploitation, how much risk to take, etc.
Switches macro decision patterns.
	•	world.py / world_model.py (WorldOS / WorldModel)
Builds a snapshot of world state from recent decisions & memory:
project progression, cumulative risk, pending tasks, etc.
Stored as JSON world_state and passed into future /v1/decide calls.

⸻

4.2 Safety, value, and self-improvement layer
	•	fuji.py (FUJI Gate)
Final safety / ethics / compliance gate.
Internally computes:
	•	risk_score
	•	violations[] (which policies are hit)
	•	status: allow | modify | block | abstain
Also exposed as a standalone API via /v1/fuji/validate.
	•	value_core.py (ValueCore)
Maintains VERITAS’s internal Value EMA (Exponential Moving Average).
Each decision updates a scalar notion of “goodness” of behavior.
Used to compute telos_score and next_value_boost.
	•	reflection.py (ReflectionOS)
Performs self-reflection from decision logs and Doctor reports:
detects patterns such as “where does it fail more often?”,
and feeds these insights back into Planner / ValueCore.
	•	adapt.py
Entry point for future self-adaptation / self-improvement
algorithms.
Currently experimental and tied to RSI and benchmark utilities.
	•	rsi.py
Notes and prototypes for Recursive Self-Improvement (RSI).
Describes which information should be fed into the next learning cycle.

⸻

4.3 Evidence, critique, and debate layer
	•	evidence.py (EvidenceOS)
Collects evidence candidates from Web search (optional),
MemoryOS, WorldModel, etc., and scores them by relevance/reliability.
Produces the structure used in DecideResponse.evidence[].
	•	critique.py (CritiqueOS)
Prompts the LLM to critique its own plan:
surface missing risks, flawed assumptions, weak reasoning, etc.
Output is consumed by FUJI and DebateOS.
		•	debate.py (DebateOS)
Runs pseudo multi-agent debates (pro, con, third-party views).
Structures arguments for each side, then summarizes them and feeds the
result back into chosen.

⸻

4.4 MemoryOS layer
	•	memory.py (MemoryOS front-end)
Manages long-term memory, usually stored in
scripts/logs/memory.json.
Saves episodes, decisions, and metadata; provides search via
MemoryOS.search().
Internally uses the modules under core/memory/.
	•	core/memory/embedder.py
Generates embedding vectors for memory entries.
Currently uses a lightweight model + caching.
	•	core/memory/engine.py
Core nearest-neighbor search engine (cosine similarity etc.).
Handles episodic.index.npz / semantic.index.npz and provides
high-speed search.
	•	core/memory/index_cosine.py
CosineIndex implementation.
Exposes low-level add() / search() APIs used by MemoryOS.
	•	core/memory/store.py
Simple storage abstraction (e.g. JSONL).
Keeps index and raw data consistent.

⸻

4.5 LLM client & logging
	•	llm_client.py
Central wrapper for accessing OpenAI (or other) LLM APIs.
Handles model selection, retries, timeouts, etc.
Upper layers can treat it as a simple function call.
	•	logging.py (common log utilities)
Helpers for writing decision/safety logs.
Log folder layout is defined in core/logging/paths.py.
	•	core/logging/dataset_writer.py
Exports decision logs as training datasets, e.g.
datasets/dataset.jsonl.
	•	core/logging/paths.py
Central definition of local paths for logs, reports, backups, etc.
Integrates with environment variables such as VERITAS_DATA_DIR.

⸻

4.6 Tone / style, curriculum, experiments
	•	affect.py
Controls tone & affect of responses
(e.g. calm, focused, empathetic).
Linked to Context.affect_hint, modifies LLM prompts accordingly.
	•	curriculum.py
Logic for building self-training / self-evaluation curricula.
Cooperates with benchmarks under docs/ and datasets/ to decide
“which tasks to practice next”.
	•	experiment.py
Utilities for AGI experiments and benchmarks.
Contains code for A/B testing and measuring Decision OS behavior.

⸻

4.7 Sanitization & utilities
	•	sanitize.py
Removes dangerous content, PII, control characters from prompts and
responses.
Separate from FUJI, this is “pure text cleaning”.
	•	tools.py
Small shared utilities: date formatting, ID generation, helpers used by
multiple modules.
	•	identity.py
VERITAS instance ID / version / metadata.
Used by Doctor Dashboard and logs to show “who this system is”.

⸻

🚀 5. Running the API server

	1.	Clone

git clone https://github.com/veritasfuji-japan/veritas_clean_test2.git
cd veritas_clean_test2

	2.	Create virtualenv

python3.11 -m venv .venv
source .venv/bin/activate

3.	Install dependencies

pip install -r requirements.txt
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

	4.	Start the server

python3 -m uvicorn veritas_os.api.server:app --reload --port 8000

5.	Call from Swagger / OpenAPI

	•	Load the OpenAPI 3.1 schema into Swagger Editor / Studio
	•	Make sure servers[0].url = http://127.0.0.1:8000
	•	Use Authorize to set X-API-Key
	•	Call POST /v1/decide with a sample JSON body and verify the response

⸻

📊 6. Doctor Dashboard

Generate a self-diagnosis report and HTML dashboard:

cd veritas_os/scripts
source ../.venv/bin/activate
python generate_report.py

Artifacts:
	•	scripts/logs/doctor_report.json
	•	scripts/logs/doctor_dashboard.html

The dashboard shows, for example:
	•	Number of decide calls over time
	•	FUJI decision distribution
	•	Memory hit counts
	•	Value EMA evolution
	•	Frequency of unsafe / modified actions
	•	Latency distribution

All in a browser-friendly view.

⸻

✅ 7. Verified environment

This setup has been tested with:
	•	macOS
	•	Python 3.11.x
	•	uvicorn + fastapi
	•	OpenAI API (gpt-series models)
	•	Swagger Editor / Swagger Studio

⸻

🧵 8. Summary
	•	VERITAS OS is an OS-layer that wraps an LLM as an AGI-style decision
engine
	•	Decision / Safety / Memory / Value / WorldModel / TrustLog are integrated
into one coherent stack
	•	The project targets researchers & companies who want to reproduce AGI / AI
Safety / Alignment experiments locally, with a focus on:
	•	repeatability
	•	auditability
	•	safety-gated decision-making

Copyright (c) 2025 Takeshi Fujishita
All Rights Reserved.
