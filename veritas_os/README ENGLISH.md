# VERITAS OS — Technical Overview (for Researchers)

**Status**: Single-user AGI-OS prototype (local only)  
**Domain**: Long-horizon decision support, self-monitoring agent  
**Author**: FUJISHITA (ERASER)  

---

## 1. Abstract

VERITAS is designed as an **“OS on top of LLMs”** –  
a *single-user, long-horizon decision agent* that runs locally.

Four key ideas:

1. **ValueCore**  
   Every decision is scored along dimensions such as ethics, legality, risk,
   user benefit, etc. The current weights are stored in `value_core.json`
   and updated over time.

2. **MemoryOS**  
   Episodic, semantic, and skill memories are stored under `memory/`
   (JSONL + vector indices). For each decision, VERITAS retrieves relevant
   memories and uses them as evidence.

3. **WorldModel + WorldState**  
   Global progress, risk, and decision statistics per project are stored
   in `world_state.json`. This acts as a “task/goal registry” for the OS.

4. **FUJI Gate + Doctor**  
   A safety layer (FUJI) and a self-monitoring layer (Doctor) wrap the
   decision pipeline, suppressing risky actions and diagnosing system health
   from logs.

This repository aims to implement the above OS in a *minimal, inspectable way*  
using only FastAPI, a CLI, and the local filesystem.

---

## 2. Repository Layout

Current structure (approximate):

```text
veritas/
  README.md
  requirements.txt
  __init__.py
  .gitignore

  api/
    server.py          # FastAPI app (/v1/decide, /api/status, etc.)
    schemas.py         # Pydantic models
    telos.py           # Telos / value configuration API
    constants.py
    ...

  core/
    config.py          # Config (API key, data_dir etc., via env or dummy)
    kernel.py          # Core decide() logic
    value_core.py      # ValueCore scoring
    world.py           # World state updates
    world_model.py     # Pydantic models for world_state.json
    planner.py         # Multi-step plan generation
    memory.py          # MemoryOS entry point
    debate.py          # Lightweight DebateOS
    critique.py        # Lightweight CritiqueOS
    fuji.py            # FUJI safety gate
    rsi.py             # self-improvement hooks (RSI placeholder)
    strategy.py        # High-level strategy decisions
    logging.py         # Structured logging
    tools.py           # Utilities
    adapt.py           # Persona / bias learning
    affect.py          # Tone / affect module
    identity.py        # Agent self-description
    llm_client.py      # LLM client abstraction
    models/
      memory_model.pkl # Lightweight encoder for MemoryOS
    ...

  memory/
    episodic.jsonl     # Episodic memory (per decision episode)
    semantic.jsonl     # Knowledge-like notes
    skills.jsonl       # Reusable skills / procedures
    episodic.index.npz # Vector index (cosine)
    semantic.index.npz # Vector index (cosine)
    skills.index.npz   # Vector index (cosine)
    memory.json        # MemoryOS metadata

  logs/
    doctor_auto.log    # Auto-health-check logs
    doctor_auto.err
    cron.log
    DASH/decide_*.json # Decision snapshots for dashboard

  reports/
    doctor_dashboard.html  # HTML dashboard (self-monitoring)
    doctor_report.json
    ...

  scripts/
    decide.py          # CLI wrapper for /v1/decide
    decide_plan.py     # Planning-oriented query templates
    health_check.py    # Aggregates logs into a Doctor report
    generate_report.py # Generates HTML dashboard
    memory_train.py    # Rebuilds MemoryOS indices
    memory_sync.py     # Syncs memory/ and ~/.veritas
    auto_heal.sh       # Lightweight auto-recovery actions
    backup_logs.sh     # trust_log backups
    sync_to_drive.sh   # Optional rclone backup
    start_server.sh    # uvicorn launcher
    veritas.sh         # CLI entrypoint wrapper
    ...

  templates/
    personas/
      default.txt      # Default persona prompt
    styles/
      concise.txt
      deep.txt
    tones/
      friendly.txt
      serious.txt

  trust_log.json       # Aggregated decision log
  trust_log.jsonl      # Line-by-line decision log
  value_core.json      # Current ValueCore weights
  value_stats.json     # Value statistics
  world_state.json     # WorldModel snapshot

3. Decision Pipeline

3.1 API Entry: /v1/decide
	•	Implemented in: api/server.py
	•	Typical request payload:

{
  "query": "natural language question / instruction",
  "alternatives": [ /* optional candidate actions */ ],
  "context": {
    "user_id": "veritas_dev",
    "stakes": 0.5,
    "telos_weights": { "W_Transcendence": 0.6, "W_Struggle": 0.4 }
  }
}

3.2 High-level Flow
	1.	FUJI Pre-check (core.fuji.pre_check)
Quick rule-based screening of the input query and stakes.
Obvious high-risk content can be blocked or have risk increased.
	2.	Memory Retrieval (core.memory.retrieve)
Query is embedded and matched against memory/episodic.jsonl,
semantic.jsonl, skills.jsonl using cosine similarity
(index_cosine.py). Top-k hits are formatted as:

{ "source": "memory:semantic", "uri": "...", "snippet": "...", "confidence": 0.12 }

3.	PlannerOS (core.planner.plan)
An LLM generates a 3–5 step micro-plan for the query:

{
  "id": "step1",
  "title": "Inspect latest logs",
  "detail": "...",
  "eta_hours": 2,
  "risk": 0.05,
  "dependencies": []
}


	4.	Kernel Decide (core.kernel.decide)
	•	Detect intent via _detect_intent (weather / health / learn / plan / …).
	•	If no alternatives are provided, generate intent-specific default options.
	•	Merge planner steps + restored options from history (if any).
	•	Load persona bias from adapt.load_persona() and clean it with
adapt.clean_bias_weights().
	•	Score each alternative using:
	•	intent-specific heuristics
	•	persona bias
	•	Telos / ValueCore coefficients
	•	Choose argmax(score) as chosen.
	•	Add an internal evidence entry describing how many alternatives were considered.
	5.	ValueCore Scoring (core.value_core.score)
Score the decision along dimensions such as:
	•	ethics, legality, harm_avoid, truthfulness,
user_benefit, reversibility, accountability,
efficiency, autonomy, etc.
Aggregate into:

{
  "total": 0.54,
  "top_factors": ["ethics", "legality", "harm_avoid", "truthfulness", "user_benefit"],
  "rationale": "Prioritized ethics / legal safety / long-term user benefit."
}

Telos is modeled as a 2-dimensional configuration:

W_T = cfg.telos_default_WT   # Transcendence
W_S = cfg.telos_default_WS   # Struggle
telos_score = 0.5 * W_T + 0.5 * W_S  # 0.0–1.0


	6.	FUJI Post-check (core.fuji.post_check)
Using the ValueCore scores and the chosen option:
	•	allow: decision passes as-is
	•	modify: rewrite or soften the instruction
	•	block: replace with “request human review” or a safe alternative
	7.	WorldModel Update (core.world.update)
For a given project ID (e.g. "veritas_agi"), VERITAS updates:
	•	decision_count
	•	progress
	•	last_risk
	•	last_decision_ts
	•	notes
The consolidated view is persisted to world_state.json.
	8.	Logging / Learning
	•	Append the full decision record to trust_log.jsonl.
	•	Update persona bias with adapt.update_persona_bias_from_history(window=50),
then normalize and write back to persona.json.
	•	This creates a slow EMA-style learning of “which options the user tends to pick”.

⸻

4. MemoryOS Design

4.1 Data Layout
	•	memory/episodic.jsonl
	•	One line per decision episode.
	•	Example:

{
  "ts": "2025-11-14T11:09:43Z",
  "query": "How to present VERITAS to researchers?",
  "decision": { "chosen": {...} },
  "tags": ["AGI", "VERITAS"]
}


	•	memory/semantic.jsonl
	•	Longer-lived knowledge and structured notes.
	•	memory/skills.jsonl
	•	Procedural knowledge (“how-to” sequences), e.g.
“Step-by-step instructions to push to GitHub”.
	•	*.index.npz
	•	Vector indices corresponding to the above JSONL files,
built with core/memory/embedder.py and memory_model.pkl.

4.2 Retrieval Algorithm (sketch)
	1.	Encode query into an embedding.
	2.	For each index (episodic / semantic / skills):
	•	Run cosine similarity search.
	3.	Filter top-k by score + recency.
	4.	Emit entries as evidence[].

Because every decision explicitly consults the agent’s own past logs and notes,
VERITAS is strongly specialized for one user.

⸻

5. ValueCore & Telos
	•	value_core.json stores current weights and stats.
	•	Telos is parameterized by two axes: "Transcendence" and "Struggle".
	•	Defaults are defined in core/config.py
(telos_default_WT, telos_default_WS), but can be overridden per request.

ValueCore scores are written to trust_log.jsonl and analyzed via:
	•	scripts/analyze_logs.py
	•	reports/doctor_dashboard.html

This enables inspection of drifts, biases, and value-dimension trends across time.

⸻

6. Safety Layer: FUJI Gate

Implemented in core/fuji.py.
	•	Pre-decision
	•	Lightweight pattern checks for self-harm, illegal activity,
privacy violations, etc.
	•	Can immediately block or raise an effective risk score.
	•	Post-decision
	•	Examines ValueCore results and the proposed action.
	•	If below thresholds, changes decision_status to block and may:
	•	provide a safer alternative,
	•	or request human review.

The goal is not a full-blown safety framework but to demonstrate
“safety as an OS layer” rather than a model-internal afterthought.

⸻

7. Self-Monitoring: Doctor / Auto-heal
	•	scripts/health_check.py
	•	Scans trust_log.jsonl and logs/*.log to compute metrics:
	•	error rate
	•	blocked decision ratio
	•	frequency of high-risk decisions
	•	trends of ValueCore scores
	•	reports/doctor_dashboard.html
	•	Visualizes these metrics in a browser-friendly dashboard.
	•	scripts/auto_heal.sh
	•	Designed to be called via cron.
	•	Based on Doctor metrics, can perform simple recovery actions such as:
	•	restarting services
	•	rotating logs
	•	rebuilding broken indices

⸻

8. LLM Integration

LLM calls are abstracted in core/llm_client.py:
	•	Exposes a thin interface like chat(model, messages, **kwargs).
	•	Concrete backend (OpenAI, Claude, Grok, local LLM, etc.) is intentionally
decoupled from the OS logic.

For research, swapping the backend allows comparison of different models
under the same OS (same MemoryOS, ValueCore, FUJI, etc.).

⸻

9. Extensibility Points

Things a researcher might want to modify or plug in:
	1.	Custom Memory Schemas
	•	Change the JSONL schemas under memory/ to experiment with
graph-like or domain-specific structures.
	2.	Extended ValueCore
	•	Add new value dimensions (e.g. sustainability, fairness, privacy)
in value_core.py and track them in value_core.json.
	3.	FUJI Plugins
	•	Introduce new safety checks (regulatory rules, enterprise policies)
as separate modules.
	4.	Tool Integration
	•	When LLMs call external tools, route them through VERITAS so that
all tool invocations are logged, scored, and safety-checked at the OS level.

⸻

10. Limitations / Non-Goals

VERITAS, in its current form, is not AGI itself. It is:
	•	single-user,
	•	local-machine,
	•	file-based,

a “proto-AGI OS layer” on top of LLMs.

Not implemented / not yet validated:
	•	multi-user, distributed deployments
	•	fully automated self-improvement loops (human-in-the-loop assumed)
	•	rigorous proofs of safety for self-modification
	•	RLHF / bandit-style formal learning

⸻

11. Positioning

From a research perspective, VERITAS sits at the intersection of:
	•	personal AI / LifeOS,
	•	an orchestration layer above tool-using LLMs,
	•	value- and safety-aware decision making,
	•	long-term memory + world-model + self-monitoring agents.

⸻

12. Access & Collaboration

This repository is currently private and intended for limited sharing
with potential research collaborators.

For collaboration proposals, please contact the author (FUJISHITA) directly.