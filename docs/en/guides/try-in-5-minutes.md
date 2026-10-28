# Try VERITAS in 5 minutes

**You need:** Python 3.11+. **You do NOT need:** an OpenAI API key, Docker, any credential, or any external service. Nothing in this guide performs a real-world effect.

## 1. Clone (about 1 minute)

```bash
git clone https://github.com/veritasfuji-japan/veritas_os.git
cd veritas_os
```

## 2. Run the boundary demo (under 1 minute)

```bash
python3 scripts/demo/validate_reviewer_evidence_packet.py
```

## 3. Read the summary (2 minutes)

Look at `aggregate_summary` in the JSON output:

- `total_cases: 5` — four unsafe proposals and one valid proposal
- `blocked_cases: 4` — missing authority, missing approval, expired approval, scope mismatch: each refused fail-closed, each with a recorded refusal basis
- `committed_cases: 1` — the one case with valid authority and approval
- `verified_chains: 5` — every case, blocked or not, carries an evidence chain that recomputes and verifies

That asymmetry is the product: a blocked action is not a silent "no" — it is evidence a reviewer can check later.

## Next steps

- See the cases and the expected fields: [External Reviewer Quickstart](../demo/external-reviewer-quickstart.md)
- Evaluate as an engineer (10–15 min): [Engineering Evaluation Quickstart](engineering-evaluation-quickstart.md)
- Try a bounded external-effect reference path (requires `pip install -e ".[dev]"` first): `python3 scripts/demo/run_external_bind_poc.py`
- Full stack (Docker, API, Mission Control): see the Quick start section of the README.
