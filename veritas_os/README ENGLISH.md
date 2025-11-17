# VERITAS OS — Proto-AGI Decision OS / Public API

> This README is for the `veritas_os/` directory inside the `veritas_clean_test2` repository.  
> Clone `veritas_clean_test2` first, then use the `veritas_os` folder as the library / API server.

---

## TL;DR

- **VERITAS OS = a framework that wraps an LLM as a Proto-AGI “Decision OS”**, rather than calling the LLM directly.
- `/v1/decide` runs a **full decision loop in one shot**:
  - option generation → evidence collection → critique → debate → safety gate (FUJI) → immutable trust log.
- Designed to be called from **OpenAPI 3.1 + Swagger Studio**, talking to a local `uvicorn` server.
- Ships with **MemoryOS / WorldModel / ValueCore / FUJI Gate / Doctor Dashboard** as one coherent “AGI skeleton”.
- Goal: an **experimental platform for using LLMs as safe, reproducible and auditable proto-AGI decision engines.**

---

## What is VERITAS OS?

Instead of “just calling the LLM API” (e.g. OpenAI), VERITAS OS wraps it as:

> **“An OS that runs the LLM as a safe, consistent and inspectable decision engine.”**

It exposes a **Proto-AGI framework / Decision OS** via a public API described by an **OpenAPI 3.1 schema** (for Swagger Studio / Editor):

- `/v1/decide` – full decision loop (ValueCore / FUJI / Memory / WorldModel / ReasonOS)
- `/v1/fuji/validate` – safety & ethics validation for a single candidate action
- `/v1/memory/*` – persistent memory put/get
- `/v1/logs/trust/{request_id}` – immutable trust-log retrieval

All endpoints are protected with **X-API-Key** authentication.

---

## 🔧 What makes VERITAS OS different?

1. **Decision-first design**

   - You don’t call the LLM directly – you call `/v1/decide`.
   - Every call returns a full decision structure:
     `chosen / alternatives / evidence / critique / debate / fuji / trust_log`.

2. **Safety & Trust as first-class APIs**

   - `/v1/fuji/validate` lets you run **only** the safety / ethics gate, independent of the main decision loop.
   - `/v1/logs/trust/{request_id}` returns a **chained trust log** so decisions can be audited later.

3. **A unified “Proto-AGI skeleton” (Memory / World / ValueCore)**

   - MemoryOS, WorldModel and ValueCore are wired into the loop.
   - Their state is surfaced both in the `DecideResponse` and in the Doctor Dashboard.

---

## 💡 Why is this useful?

### 1. You don’t just get an answer, you get a **decision process**

`POST /v1/decide` returns, following the Swagger `DecideResponse` schema:

- `chosen`
  - `action`: short description of **the one step to take now**
  - `rationale`: why that step was chosen
  - `uncertainty`: 0–1 uncertainty score
- `alternatives[]` (`Option`)
  - other candidate options that were considered
- `evidence[]` (`EvidenceItem`)
  - which pieces of evidence were used as justification
- `critique[]` / `debate[]`
  - internal self-critique and pseudo-debate views
- `telos_score`
  - alignment score against the current value / goal configuration
- `fuji` (`FujiDecision`)
  - safety / ethics gate result: `allow | modify | block | abstain`
- `trust_log`
  - immutable trust log entry with `sha256_prev` for chaining

> In other words: **“Why did it choose this action?” is always structured.**  
> This makes VERITAS suitable for AGI research, safety evaluation and audit workflows.

---

### 2. You can treat AGI-style tasks as **framework-level decisions**

The `Context` schema (from the Swagger definition) looks like this:

```yaml
Context:
  type: object
  required: [user_id, query]
  properties:
    user_id: {type: string}
    session_id: {type: string}
    query: {type: string, description: "User query / problem statement"}
    goals: {type: array, items: {type: string}}
    constraints: {type: array, items: {type: string}}
    time_horizon: {type: string, enum: ["short","mid","long"]}
    preferences: {type: object}
    tools_allowed: {type: array, items: {type: string}}
    telos_weights:
      type: object
      properties:
        W_Transcendence: {type: number}
        W_Struggle: {type: number}
    affect_hint: {type: string, enum: ["calm","focused","empathetic","concise"]}

For AGI-ish questions, you feed in:
	•	medium / long-term time_horizon
	•	value weights in telos_weights
	•	allowed tools in tools_allowed
	•	preferred response tone in affect_hint

So you can ask VERITAS to handle “meta-decisions for an AGI project”.

Example – choose the shortest path to an MVP demo:

“What is the fastest plan to ship a VERITAS AGI-framework MVP demo that a third party can understand?”

{
  "context": {
    "user_id": "fujishita",
    "session_id": "sess-agi-mvp-001",
    "query": "Fastest plan to ship a VERITAS AGI-framework MVP demo that third parties can understand",
    "goals": [
      "Build a demo that explains VERITAS in 10 minutes",
      "Clearly communicate the AGI framework skeleton"
    ],
    "constraints": [
      "Finish within this week",
      "Use only local environment + GitHub + Swagger Studio"
    ],
    "time_horizon": "short",
    "telos_weights": {
      "W_Transcendence": 0.6,
      "W_Struggle": 0.4
    },
    "affect_hint": "focused"
  },
  "options": [],
  "min_evidence": 2,
  "stream": false
}

/v1/decide will then:
	•	list candidate step sequences in alternatives[]
	•	pick the first step to execute this week in chosen.action
	•	expose quality & safety via telos_score and fuji.status

Effectively, it becomes a “command API for AGI projects”.

⸻

3. Safety gate, memory and trust are all exposed as APIs

The Swagger definition maps to the following endpoints
(all require an X-API-Key header):

GET /health
	•	Simple health check. Returns 200 if the server is up.

POST /v1/decide
	•	Full decision loop.
	•	Request body: context (as above) + optional options[] / min_evidence / stream
	•	Response: DecideResponse (chosen / alternatives / evidence / fuji / trust_log / …)

POST /v1/fuji/validate
	•	Safety & ethics validation for a single action + context.

Example:

{
  "action": "Run the user-specified AGI experiment on production data",
  "context": {
    "user_id": "fujishita",
    "query": "Is this experiment safe to run?",
    "time_horizon": "mid"
  }
}

	•	Response: FujiDecision
	•	status: allow | modify | block | abstain
	•	reasons[], violations[]

POST /v1/memory/put
	•	Append to persistent memory:

{
  "user_id": "fujishita",
  "key": "veritas_agi_todos",
  "value": "Priority TODO list for the AGI MVP v1"
}

GET /v1/memory/get
	•	Retrieve value by user_id + key.

GET /v1/logs/trust/{request_id}
	•	Retrieve the immutable trust log created during /v1/decide.
	•	Because entries are chained via sha256_prev, you can track when, on what basis and who approved each decision.

⸻

🌐 Using OpenAPI / Swagger Studio

The OpenAPI schema (the YAML you paste into Swagger Studio) is:
	•	openapi: 3.1.0
	•	info.title: VERITAS Public API
	•	servers[0].url: http://127.0.0.1:8000
	•	securitySchemes.ApiKeyAuth:
	•	type: apiKey
	•	in: header
	•	name: X-API-Key

Typical flow in Swagger Studio / Editor:
	1.	Open Swagger Editor / Swagger Studio.
	2.	Paste the OpenAPI YAML into the left pane.
	3.	Confirm servers[0].url is http://127.0.0.1:8000.
	4.	Click Authorize, select ApiKeyAuth, and enter your X-API-Key.
	5.	Choose POST /v1/decide, click Try it out, and send a JSON payload like the AGI example above.

Your local uvicorn veritas_os.api.server:app responds, and the Editor shows a DecideResponse JSON matching the schema.

This gives you a “Swagger-driven Proto-AGI OS dev style”: experiment with decision loops live from the OpenAPI UI.

⸻

🛠 Setup (assuming you pull veritas_clean_test2)

The veritas_os directory lives inside the veritas_clean_test2 repository.

0. Clone the repository

cd ~
git clone https://github.com/veritasfuji-japan/veritas_clean_test2.git
cd veritas_clean_test2

Project layout

veritas_os/
├─ api/                      # Public API & dashboard
│  ├─ __init__.py
│  ├─ constants.py           # Shared constants
│  ├─ dashboard_server.py    # Simple server for Doctor Dashboard
│  ├─ evolver.py             # Future self-improvement API scaffold
│  ├─ merge_trust_logs.py    # Tool for merging trust logs
│  ├─ schemas.py             # FastAPI / Pydantic schemas
│  ├─ server.py              # Main API (/v1/decide, /v1/fuji, …)
│  └─ telos.py               # Telos (value weights) helpers
│
├─ core/                     # Central VERITAS logic (AGI skeleton)
│  ├─ __init__.py
│  ├─ models/
│  │  ├─ __init__.py
│  │  └─ memory_model.pkl    # Embedding model for MemoryOS
│  ├─ adapt.py               # Self-adaptation logic (future use)
│  ├─ affect.py              # Tone / affect control
│  ├─ critique.py            # CritiqueOS: self-critique phase
│  ├─ debate.py              # DebateOS: multi-view pseudo-debate
│  ├─ evidence.py            # EvidenceOS: evidence retrieval & scoring
│  ├─ fuji.py                # FUJI Gate: safety / ethics decisions
│  ├─ identity.py            # System identity / meta-info
│  ├─ kernel.py              # Core kernel wiring all OS modules
│  ├─ llm_client.py          # OpenAI API wrapper
│  ├─ logging.py             # Logging utilities
│  ├─ memory.py              # MemoryOS: long-term memory manager
│  ├─ planner.py             # PlannerOS: step decomposition
│  ├─ reason.py              # ReasonOS: reasoning chains
│  ├─ reflection.py          # ReflectionOS: self-reflection
│  ├─ rsi.py                 # RSI / self-improvement notes (experimental)
│  ├─ sanitize.py            # Input/output sanitisation
│  ├─ strategy.py            # High-level strategy logic
│  ├─ tools.py               # Helper tools
│  ├─ value_core.py          # ValueCore: EMA / next_value_boost
│  ├─ world.py               # WorldOS: state update helpers
│  ├─ world_model.py         # WorldModel: world snapshots
│  │
│  ├─ logging/               # Logging submodules
│  │  ├─ __init__.py
│  │  ├─ dataset_writer.py   # Export training data
│  │  └─ paths.py            # Log path management
│  │
│  └─ memory/                # Vector store / search modules
│     ├─ __init__.py
│     ├─ embedder.py         # Embedding generator
│     ├─ engine.py           # Retrieval engine
│     ├─ episodic.index.npz  # Nearest-neighbour index
│     ├─ index_cosine.py     # Cosine similarity search
│     └─ store.py            # Storage layer
│
├─ scripts/                  # CLI tools & ops scripts
│  ├─ alert_doctor.py        # Send Slack alerts from doctor_report
│  ├─ analyze_logs.py        # Summarise decision logs
│  ├─ auto_heal.sh           # Auto-recovery (experimental)
│  ├─ backup_logs.sh         # Zip backups of logs
│  ├─ decide.py              # CLI helper for /v1/decide
│  ├─ decide_plan.py         # Planning-focused decide wrapper
│  ├─ doctor.py              # Generate doctor_report.json
│  ├─ doctor.sh              # Run doctor → report in one shot
│  ├─ generate_report.py     # Render HTML Doctor Dashboard
│  ├─ heal.sh                # Simple health check & repair
│  ├─ health_check.py        # API health check
│  ├─ memory_sync.py         # Sync memory.json
│  ├─ memory_train.py        # Retrain MemoryOS embeddings
│  ├─ notify_slack.py        # Slack notification helper
│  ├─ start_server.sh        # Start uvicorn server
│  ├─ sync_to_drive.sh       # Google Drive backup via rclone
│  ├─ veritas.sh             # Top-level CLI (full / decide / report …)
│  └─ veritas_monitor.sh     # Periodic monitoring / self-diagnosis loop
│
├─ templates/
│  ├─ personas/              # Agent persona templates
│  ├─ styles/                # Output style templates
│  └─ tones/                 # Tone presets
│
├─ README.md                 # Japanese documentation
├─ README_ENGLISH.md         # This file
├─ requirements.txt          # Python dependencies
└─ .gitignore

1. Create a Python virtual environment

cd ~/veritas_clean_test2

# If Python 3.11 is not installed:
brew install python@3.11

python3.11 -m venv .venv
source .venv/bin/activate

2. Install dependencies

cd ~/veritas_clean_test2/veritas_os
source ../.venv/bin/activate

export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

pip install --upgrade pip
pip install joblib
pip install requests
pip install matplotlib
pip install "openai>=1.0.0" scikit-learn

pip install -r requirements.txt

3. Use a separate data directory (recommended)

cd ~/veritas_clean_test2
export VERITAS_DATA_DIR=~/veritas_clean_test2/data
mkdir -p "$VERITAS_DATA_DIR"

All runtime artefacts (e.g. trust_log.json, world_state.json, memory snapshots) will be written under this directory.

⸻

4. Start the API server

cd ~/veritas_clean_test2
source .venv/bin/activate

python3 -m uvicorn veritas_os.api.server:app --reload --port 8000

•	Confirm that http://127.0.0.1:8000 matches the servers[0].url in your OpenAPI schema.
	•	When you see Application startup complete. in the logs, the server is ready.

⸻

🩺 Generating the Doctor Dashboard

To create a self-diagnostic HTML report from logs:

cd ~/veritas_clean_test2/veritas_os/scripts
source ../.venv/bin/activate

python generate_report.py

Outputs:
	•	scripts/logs/doctor_report.json
	•	scripts/logs/doctor_dashboard.html

The dashboard visualises:
	•	daily count of decisions
	•	FUJI status distribution
	•	latency trends
	•	number of memory evidences used
	•	Value EMA over time
	•	redaction / modification frequency
	•	memory hit-rate

These internal metrics are not visible in a single DecideResponse, but are crucial for monitoring and research.

⸻

✅ Verified runtime environment

This configuration has been tested with:
	•	macOS
	•	Python 3.11.14
	•	veritas_clean_test2 cloned from GitHub
	•	python3.11 -m venv .venv → pip install -r requirements.txt
	•	python3 -m uvicorn veritas_os.api.server:app --reload --port 8000
	•	OpenAPI 3.1 schema pasted into Swagger Studio / Editor
	•	After setting X-API-Key, POST /v1/decide successfully handled AGI-style queries
and returned valid DecideResponse objects (as of 2025-11-15).

⸻

In one sentence
	•	VERITAS OS exposes LLMs as a public HTTP API for AGI-style decision-making,
	•	when paired with Swagger Studio + OpenAPI 3.1, it enables:
	•	reproducible experiments,
	•	auditable trust logs,
	•	safety-gated decision loops,

all accessible over a clean REST interface.

⸻

For researchers

This repository is intended as a local, reproducible playground for AGI / AI Safety / AI Alignment work:
	•	experimenting with a “Decision OS” architecture,
	•	evaluating safety of LLM-based agents, and
	•	analysing the behaviour of agents with long-term memory + chained trust logs.

Pull it, spin it up, and treat /v1/decide as the control panel for your proto-AGI experiments.

Copyright (c) 2025 Takeshi Fujishita
All rights reserved.
