# VERITAS OS v2.0 — Proto-AGI Decision OS

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.17688094.svg)](https://doi.org/10.5281/zenodo.17688094)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-red.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-Production%20Ready%20(98%25)-green.svg)]()
[![CI](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml/badge.svg)](https://github.com/veritasfuji-japan/veritas_os/actions/workflows/main.yml)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](../docs/COVERAGE_REPORT.md)


**Version**: 2.0.0
**Release Date**: 2025-12-01  
**Author**: Takeshi Fujishita

This repository contains **VERITAS OS** — a **Proto-AGI framework** that wraps an LLM  
(e.g. **OpenAI GPT-4.1-mini**) as a **safe, consistent, and auditable decision OS**.

- Mental model: **“LLM = CPU”**, **“VERITAS OS = Decision / Agent OS on top”**

**Readmes**

- **English README** (this file)
- **Japanese README**: [`README_JP.md`](README_JP.md) *(optional / if present)*

---

## 📑 Table of Contents

1. [What can it do?](#-1-what-can-it-do)
2. [Context Schema (for AGI tasks)](#-2-context-schema-for-agi-tasks)
3. [Directory Layout](#-3-directory-layout)
4. [core/ Module Responsibilities](#-4-core-module-responsibilities)
5. [LLM Client](#-5-llm-client)
6. [TrustLog & Dataset](#-6-trustlog--dataset)
7. [Doctor Dashboard](#-7-doctor-dashboard)
8. [Quickstart](#-8-quickstart)
9. [Development Guide](#-9-development-guide)
10. [Troubleshooting](#-10-troubleshooting)
11. [License](#-11-license)
12. [Contributing / Acknowledgements / Contact](#-12-contributing--acknowledgements--contact)

---

## 🎯 1. What can it do?

### 1.1 `/v1/decide` — Full Decision Loop

`POST /v1/decide` always returns a **structured JSON** with the full decision context.

Key fields (simplified):

| Field              | Description                                                                                           |
|--------------------|-------------------------------------------------------------------------------------------------------|
| `chosen`           | Selected action (description, rationale, uncertainty, utility, risk, etc.)                           |
| `alternatives[]`   | Other candidate actions / options                                                                     |
| `evidence[]`       | Evidence used (MemoryOS / WorldModel / web, etc.)                                                    |
| `critique[]`       | Self-critique and identified weaknesses                                                              |
| `debate[]`         | Pseudo multi-agent debate results (pro / con / third-party views)                                    |
| `telos_score`      | Alignment score vs. ValueCore’s value function                                                       |
| `fuji`             | FUJI Gate safety / ethics judgement (allow / modify / rejected)                                      |
| `gate.decision_status` | Final decision status (Enum `DecisionStatus`)                                                    |
| `trust_log`        | Hash-chained TrustLog entry with `sha256_prev` (for auditability)                                   |

Pipeline mental model:

```text
Options → Evidence → Critique → Debate → Planner → ValueCore → FUJI → TrustLog
(Local FastAPI server with OpenAPI 3.1 / Swagger UI, no external deps after startup)
````

Bundled subsystems:

* **MemoryOS** – long-term episodic / semantic memory
* **WorldModel** – world state & ongoing projects
* **ValueCore** – value function / Value EMA
* **FUJI Gate** – safety & compliance gate
* **TrustLog** – cryptographic, hash-chained decision log
* **Doctor Dashboard** – self-diagnostics & health monitoring

**Goal:** Research & experimentation platform for using LLMs as
**safe, reproducible, and cryptographically auditable Proto-AGI skeletons.**

Typical use cases:

* AGI / agent **research**
* **AI Safety** experiments
* Enterprise / regulated-environment **audit pipelines**

### 1.2 Other APIs

All protected endpoints require `X-API-Key` authentication.

| Method | Path                  | Description                                    |
| ------ | --------------------- | ---------------------------------------------- |
| GET    | `/health`             | Server health check                            |
| POST   | `/v1/decide`          | Full decision loop                             |
| POST   | `/v1/fuji/validate`   | Safety / ethics validation for a single action |
| POST   | `/v1/memory/put`      | Persist information into MemoryOS              |
| GET    | `/v1/memory/get`      | Retrieve from MemoryOS                         |
| GET    | `/v1/logs/trust/{id}` | Immutable TrustLog entry (hash chain) by ID    |

---

## 🧠 2. Context Schema (for AGI tasks)

For meta-decision tasks (AGI-ish planning, self-improvement, etc.) VERITAS expects a `Context` object:

```yaml
Context:
  type: object
  required: [user_id, query]
  properties:
    user_id:      { type: string }
    session_id:   { type: string }
    query:        { type: string, description: "User request / problem statement" }
    goals:        { type: array, items: { type: string } }
    constraints:  { type: array, items: { type: string } }
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
```

Typical queries you can hand off to `/v1/decide`:

* “What is the optimal next step in my AGI research plan?”
* “How should I design my self-improvement loop?”
* “Within my safety boundaries, how far can I push this experiment?”

The OS decides **both** the multi-step plan and the immediate next action.

---

## 🏗 3. Directory Layout

### 3.1 Root Layout

```text
veritas_os/
├── chainlit_app.py
├── docs/en/notes/docs/en/notes/chainlit.md
├── data/
│   └── value_stats.json
├── docs/
│   ├── images/
│   │   ├── architecture.png
│   │   ├── pipeline.png
│   │   └── modules.png
│   ├── agi_self_hosting.md
│   ├── bench_summary.md
│   ├── fail_safe.md
│   ├── fuji_gate_safety.md
│   ├── metrics.md
│   ├── module_responsibilities.md
│   ├── self_improvement_commands.md
│   └── worldmodelstep1.md
├── veritas_os/
│   ├── api/
│   ├── core/
│   ├── logging/
│   ├── memory/
│   ├── tools/
│   ├── templates/
│   ├── scripts/
│   ├── README_JP.md
│   ├── README_ENGLISH.md       # (optional) extra English docs
│   └── requirements.txt
├── reports/
├── backups/
├── datasets/
├── veritas.sh                  # Helper shell script for local usage
├── .gitignore
└── LICENSE
```

Auto-generated directories such as `__pycache__` are omitted.

### 3.2 `veritas_os/core/` Overview

```text
veritas_os/core/
├── __init__.py
├── adapt.py
├── affect.py
├── agi_goals.py
├── code_planner.py
├── config.py
├── critique.py
├── curriculum.py
├── debate.py
├── decision_status.py
├── doctor.py
├── evidence.py
├── experiment.py
├── fuji.py
├── identity.py
├── kernel.py
├── llm_client.py
├── logging.py
├── memory.py
├── pipeline.py
├── planner.py
├── reason.py
├── reflection.py
├── rsi.py
├── sanitize.py
├── strategy.py
├── time_utils.py
├── value_core.py
├── world.py
├── world_model.py.old          # legacy world model prototype
└── models/
    ├── __init__.py
    ├── memory_model.py
    ├── memory_model.py.old     # legacy variant
    └── vector_index.json       # vector index for MemoryOS (pickle is blocked)
```

---

## 🧩 4. core/ Module Responsibilities

### 4.1 Core OS Layer

#### `kernel.py`

Global orchestrator of VERITAS.

* Entry point for `/v1/decide`
* Executes full pipeline:

```text
Planner → Evidence → Critique → Debate → FUJI → World/Memory update
```

* Assembles the final `DecideResult` JSON

#### `pipeline.py`

Orchestrator for the `/v1/decide` decision pipeline:

* `run_decide_pipeline()` is the single entry-point for `/v1/decide`
* Delegates to responsibility-separated stage modules (`pipeline_inputs`,
  `pipeline_execute`, `pipeline_policy`, `pipeline_response`, `pipeline_persist`)
* Pure utility functions live in `pipeline_compat.py` (re-exported for backward compat)
* Web search core logic lives in `pipeline_web_adapter.py`

#### `planner.py` (PlannerOS)

Transforms `query / goals / constraints` into a multi-step plan.

Produces both:

* The **immediate next action**, and
* A **longer-horizon plan** `steps[]`

#### `reason.py` (ReasonOS)

Handles internal reasoning / chain-of-thought (CoT).

* Integrates Evidence / Critique into coherent reasoning
* Provides the trace / rationale backbone of `DecideResponse`

#### `strategy.py`

High-level strategy controller (experimental):

* Exploration vs exploitation
* How much risk to take now vs later
* Switches between macro decision patterns

#### `world.py` / `world_model.py.old` (WorldOS / WorldModel)

Maintains snapshots of the world state:

* Ongoing projects / progress
* Accumulated risk / pending tasks

Stored as JSON (`world_state`) and passed forward into future `/v1/decide` calls.

---

### 4.2 Safety / Value / Self-Improvement Layer

#### `fuji.py` (FUJI Gate)

Final safety / ethics / compliance gate.

Outputs:

* `risk_score`
* `violations[]` (which policies were triggered)
* `status: allow | modify | rejected`

Usable standalone via `POST /v1/fuji/validate`.

#### `decision_status.py`

Enum for normalized decision status used across the OS:

```python
class DecisionStatus(str, Enum):
    ALLOW    = "allow"
    MODIFY   = "modify"
    REJECTED = "rejected"
```

String constants for backward compatibility are also provided.

#### `value_core.py` (ValueCore)

Manages VERITAS’ **Value EMA** (Exponential Moving Average).

* Logs a scalar “goodness” metric for each decision
* Used to compute `telos_score` and for future policy adjustments

#### `reflection.py` (ReflectionOS)

Performs self-reflection based on past decisions and Doctor Reports:

* When / where failures are likely
* Which questions / patterns the system is weak at
* Feeds back into Planner / ValueCore

#### `adapt.py` / `rsi.py`

Entry points for future self-adaptation / RSI (recursive self-improvement) logic.

* Experimental implementations & notes
* Decide which information flows into the next learning cycle

---

### 4.3 Evidence / Critique / Debate

#### `evidence.py` (EvidenceOS)

Gathers candidate evidence from:

* MemoryOS
* WorldModel
* (Optionally) web / external tools

Then scores them by relevance / reliability and populates `evidence[]`.

#### `critique.py` (CritiqueOS)

LLM-driven self-critique and verification.

* Surfaces hidden risks
* Exposes incorrect assumptions
* Feeds into FUJI / DebateOS

#### `debate.py` (DebateOS)

Runs pseudo multi-agent debates:

* Pro / con / third-party viewpoints
* Aggregates arguments into structured `debate[]`
* Influences final chosen action

---

### 4.4 MemoryOS

#### `memory.py` (MemoryOS Frontend)

Manages long-term memory centered around `scripts/logs/memory.json` (exact path configurable):

* Stores episodes / decisions / metadata
* Supports similarity-based retrieval of past decisions
* Internally uses `core/models/memory_model.py` and `vector_index.json`
* Legacy `.pkl` artifacts are blocked at runtime due to RCE risk

It also provides higher-level utilities such as:

* Semantic search with vector index + KVS fallback
* Episodic→semantic distillation (long-term “summary notes”)
* Rebuilding vector index from existing memory

#### `models/memory_model.py` / `models/vector_index.json`

Implements the embedding model and vector index used by MemoryOS.

* Handles vectorization and nearest-neighbor search
* Provides basic semantic memory capabilities

---

### 4.5 LLM Client & Logging

#### `llm_client.py`

Single entry point for **all** LLM calls.

Current v2.0 assumptions:

* Provider: **OpenAI**
* Model: `gpt-4.1-mini` (or compatible) via Chat Completions API

Controlled via environment variables:

```bash
export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"      # currently effectively 'openai'
export LLM_MODEL="gpt-4.1-mini"
export LLM_TIMEOUT="60"
export LLM_MAX_RETRIES="3"
```

`llm_client.chat(...)` is used by **Planner / Evidence / Critique / Debate / FUJI**,
so you can swap models centrally without touching the rest of the OS.

Multi-provider support (Claude / Gemini / local models) is partially stubbed and will be extended in future versions.

#### `logging.py`

Shared logging utilities across the OS.

Implements the **TrustLog hash chain** as described in the paper:

```text
h_t = SHA256(h_{t-1} || r_t)
```

* `sha256_prev` and `sha256` are automatically filled
* Log entries are appended as JSONL
* Supports cryptographic verification of the decision history

---

### 4.6 Logging / Dataset / Paths

#### `veritas_os/logging/dataset_writer.py`

Converts decision logs into a reusable dataset for future training.

Main functions:

* `build_dataset_record(req, res, meta, eval_meta)`
  → builds a normalized record per decision
* `append_dataset_record(record, path=DATASET_JSONL)`
  → appends to `datasets/dataset.jsonl`
* `get_dataset_stats()`
  → aggregates statistics: status distribution, memory usage, average score, date range
* `search_dataset(query, status, memory_used, limit)`
  → simple search API over `dataset.jsonl`

Records include `DecisionStatus`-based labels:

* `labels.status = "allow" | "modify" | "rejected"`

Plus `memory_used`, `telos_score`, `utility`, etc.

This allows extracting **“good & safe decisions”** as supervised training data for:

* Fine-tuning
* Offline evaluation
* Safety analysis

#### `veritas_os/logging/paths.py`

Centralized path definitions for:

* Logs
* Reports
* Backups
* Datasets

Works together with environment variables such as `VERITAS_DATA_DIR`.

---

### 4.7 Affect / Curriculum / Experiment / Tools

#### `affect.py`

Controls **response tone / affect**:

* Modes like `calm`, `focused`, `empathetic`, `concise`
* Driven by `Context.affect_hint`
* Modifies prompt style fed into the LLM

#### `curriculum.py` / `experiment.py`

Self-training and AGI experiment utilities:

* Generate curricula from benchmarks (e.g., `docs/bench_summary.md`)
* Run experiments / A/B tests on the decision pipeline

#### `sanitize.py`

Text sanitization layer for:

* PII removal
* Control characters
* Potentially dangerous content

This is separate from FUJI Gate and focuses on **pure text cleaning**.

#### `tools.py` / `identity.py`

* `tools.py`: Common utility functions (IDs, datetime formatting, etc.)
* `identity.py`: System identity & metadata

  * System ID
  * Version
  * “Self-intro” information used in Doctor Dashboard and logs

---

## 🧠 5. LLM Client

Summarizing:

* **Provider**: OpenAI
* **Model**: `gpt-4.1-mini` (or compatible)
* **API**: Chat Completions

Example environment configuration:

```bash
export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4.1-mini"
export LLM_TIMEOUT="60"
export LLM_MAX_RETRIES="3"
```

All internal modules call LLMs only through `llm_client`,
so you can:

* Swap models
* Switch providers (once supported)
* Control timeouts / retries / logging

from a **single place**.

---

## 🔐 6. TrustLog & Dataset

### 6.1 TrustLog (Hash-Chain Audit Log)

Implementation: `veritas_os/core/logging.py`
Output: e.g., `scripts/logs/trust_log*.jsonl`
Format: JSON Lines (1 entry per line)

Each entry contains:

* `sha256_prev`: previous entry’s `sha256`
* `sha256`: `SHA256(sha256_prev || entry_without_hashes)`

You can merge and re-hash logs while preserving integrity:

```bash
cd veritas_os
python -m veritas_os.api.merge_trust_logs \
  --out scripts/logs/trust_log_merged.jsonl
```

* Default: auto-discover existing logs, deduplicate by `request_id` / timestamp
* `--no-rehash` can disable recomputation (recommended to keep rehash **ON**)

### 6.2 Dataset Output

Decisions can be exported as training data via `dataset_writer.py`:

```python
from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
    get_dataset_stats,
    search_dataset,
)
```

Output file: `datasets/dataset.jsonl`

Contains:

* `labels.status = allow / modify / rejected`
* `memory_used`, `telos_score`, `utility`, `risk`, etc.

This makes it easy to build **“safe & high-quality decision datasets”** for:

* Fine-tuning
* Offline evaluation
* Safety analysis

---

## 📊 7. Doctor Dashboard

The **Doctor Dashboard** visualizes the health of VERITAS OS.

### 7.1 Generating the Report

```bash
cd veritas_os/scripts
source ../.venv/bin/activate
python generate_report.py
```

Outputs:

* `scripts/logs/doctor_report.json`
* `scripts/logs/doctor_dashboard.html`

Typical contents:

* Number of `/v1/decide` calls over time
* FUJI decision distribution (allow / modify / rejected)
* MemoryOS hit counts
* Value EMA evolution
* Frequency of unsafe / modified actions
* Latency distribution

Open `doctor_dashboard.html` in a browser to inspect.

### 7.2 Authenticated Dashboard Server (Optional)

You can serve the dashboard with HTTP Basic Auth using `dashboard_server.py`:

```bash
export DASHBOARD_USERNAME="veritas"
export DASHBOARD_PASSWORD="your_secure_password"
export VERITAS_LOG_DIR="/path/to/veritas_os/scripts/logs"  # optional

python veritas_os/api/dashboard_server.py
# or
python veritas_os/scripts/dashboard_server.py
```

Endpoints:

* UI: `http://localhost:8000/` or `/dashboard`
* Status API: `GET /api/status`
  → Returns `drive_sync_status.json` as JSON
* Health (no auth): `GET /health`

---

## 🚀 8. Quickstart

### 8.1 Installation

```bash
# 1. Clone
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os

# 2. Virtualenv
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r veritas_os/requirements.txt

# 4. Required environment variables
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
export VERITAS_API_KEY="your-secret-api-key"  # used for X-API-Key auth
```

### 8.2 Start the API Server

```bash
python3 -m uvicorn veritas_os.api.server:app --reload --port 8000
```

### 8.3 Test via Swagger UI

1. Open: `http://127.0.0.1:8000/docs`
2. Click **“Authorize”**
3. Add header `X-API-Key` with your `VERITAS_API_KEY` value
4. Select `POST /v1/decide`
5. Use a sample payload like:

```json
{
  "query": "Should I check tomorrow's weather before going out?",
  "context": {
    "user_id": "test_user",
    "goals": ["health", "efficiency"],
    "constraints": ["time limit"]
  }
}
```

### 8.4 Test via `curl`

```bash
curl -X POST "http://127.0.0.1:8000/v1/decide" \
  -H "X-API-Key: your-secret-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Should I check tomorrow'\''s weather before going out?",
    "context": {
      "user_id": "test_user",
      "goals": ["health", "efficiency"]
    }
  }'
```

---

## 🛠 9. Development Guide

### 9.1 Dev Environment

If you have dev requirements:

```bash
# Dev dependencies (if present)
pip install -r requirements-dev.txt

# pre-commit hooks (if configured)
pre-commit install
```

### 9.2 Tests

```bash
# Unit tests
pytest tests/

# Coverage
pytest --cov=veritas_os tests/
```

(At the time of writing, the internal test suite covers the majority of core logic.)

### 9.3 Code Quality

```bash
# Linting
flake8 veritas_os/
pylint veritas_os/

# Formatting
black veritas_os/
isort veritas_os/

# Type checking
mypy veritas_os/
```

---

## ❓ 10. Troubleshooting

### `OPENAI_API_KEY` not found

Set the environment variable:

```bash
echo $OPENAI_API_KEY
export OPENAI_API_KEY="sk-..."
```

### Port 8000 already in use

Use another port:

```bash
uvicorn veritas_os.api.server:app --reload --port 8001
```

### Memory not persisted

Check `VERITAS_DATA_DIR` and filesystem permissions:

```bash
export VERITAS_DATA_DIR="/path/to/veritas_data"
mkdir -p "$VERITAS_DATA_DIR"
```

### TrustLog verification fails

Verify merged logs (if you have a verifier script):

```bash
cd veritas_os/scripts
python verify_trust_log.py          # if implemented
# or
python ../api/merge_trust_logs.py --out logs/trust_log_merged.jsonl
```

---

## 📜 11. License

This repository uses a **mixed licensing model**.

* **Core engine & most code** (e.g. `veritas_os/`, `scripts/`, `tools/`, `config/`, `tests/`):
  **All Rights Reserved**
  → See the top-level [`LICENSE`](LICENSE) file.

* **Some subdirectories** (e.g. `docs/`, `examples/`) **may** have their own LICENSE files
  (for example, Apache License 2.0) that apply **only to those subtrees**.

**Default rule**:
If a directory/file does **not** contain its own LICENSE, assume it is **proprietary and All Rights Reserved**.

```text
Copyright (c) 2025 Takeshi Fujishita
All Rights Reserved.
```

For academic use, please cite the DOI:

```bibtex
@software{veritas_os_2025,
  author = {Fujishita, Takeshi},
  title  = {VERITAS OS: Proto-AGI Decision OS},
  year   = {2025},
  doi    = {10.5281/zenodo.17688094},
  url    = {https://github.com/veritasfuji-japan/veritas_os}
}
```

For commercial or other licensing inquiries, please contact the author.

---

## 🤝 12. Contributing / Acknowledgements / Contact

### Contributing

Pull requests are welcome, but because the core is **All Rights Reserved**,
contributions may be accepted under a contributor agreement at the owner’s discretion.

Typical workflow:

```bash
# 1. Fork the repository
# 2. Create a feature branch
git checkout -b feature/AmazingFeature

# 3. Commit your changes
git commit -m "Add some AmazingFeature"

# 4. Push to your branch
git push origin feature/AmazingFeature

# 5. Open a Pull Request on GitHub
```

If present, please check `CONTRIBUTING.md` for more details.

### Acknowledgements

This project is influenced by:

* OpenAI GPT series
* Anthropic Claude
* The AI Safety research community
* The AGI research community

### Contact

* GitHub Issues: [https://github.com/veritasfuji-japan/veritas_os/issues](https://github.com/veritasfuji-japan/veritas_os/issues)
* Email: `veritas.fuji@gmail.com`

---

**VERITAS OS v2.0 — Safe, Auditable, Proto-AGI Decision OS**

© 2025 Takeshi Fujishita. **All Rights Reserved.**
