# VERITAS OS — 3-Minute Demo Script

## Pre-requisites

```bash
# Terminal 1: Start backend
VERITAS_API_KEY=demo-key python -m uvicorn veritas_os.api.server:app --port 8000

# Terminal 2: Start frontend
cd frontend && NEXT_PUBLIC_VERITAS_API_KEY=demo-key pnpm dev
```

Open browser to `http://localhost:3000`.

---

## Act 1: Decision Console (60 sec)

1. Navigate to **Decision Console** (`/console`)
2. Enter API key: `demo-key`
3. Click a **danger preset** (e.g. "社内認証を迂回して...")
4. Observe the result:
   - `decision_status` = **rejected**
   - `fuji/gate` shows **block** or **rejected** with reasons
   - `evidence`, `critique`, `debate` stages populated
   - `trust_log` entry created with `request_id`
5. Copy the `request_id` for Act 2

**Talking point:** "FUJI Gate detected dangerous intent and blocked the request. Every decision is auditable."

---

## Act 2: TrustLog Audit (60 sec)

1. Navigate to **TrustLog Explorer** (`/audit`)
2. Click **"最新ログを読み込み"** to load recent trust logs
3. See the timeline populate with decision stages (evidence, critique, debate, fuji, etc.)
4. Paste the `request_id` from Act 1 into the search box
5. Click **"検索"** to filter
6. Select an entry to view the full JSON, including:
   - `sha256_prev` (hash chain for tamper evidence)
   - `risk` score
   - `violations`

**Talking point:** "Every decision is hash-chained. You can verify integrity and trace any decision back to its root."

---

## Act 3: Governance Control (60 sec)

1. Navigate to **Governance Control** (`/governance`)
2. Policy auto-loads. See four control sections:

   a. **FUJI Rules** — Toggle `PII Check` OFF
   b. **Risk Thresholds** — Slide `Allow Upper` from 0.40 to 0.50
   c. **Auto-Stop Conditions** — Change max consecutive rejects to 10
   d. **Log Retention** — Change retention from 90 to 180 days

3. Observe the **Diff Preview** updating in real-time:
   - Red strikethrough = before
   - Green = after
4. Click **"ポリシーを保存"**
5. See success message: "ポリシーを更新しました。"
6. Reload the page to verify persistence

**Talking point:** "Policy changes are instantly reflected and persisted. The diff preview ensures you know exactly what changed before committing."

---

## Summary (wrap-up)

| Feature | Endpoint | What it proves |
|---------|----------|----------------|
| Decision Pipeline | POST /v1/decide | 7-stage AI decision with safety gate |
| Audit Trail | GET /v1/trust/logs | Hash-chained, tamper-evident logging |
| Governance API | GET/PUT /v1/governance/policy | Real-time policy control with diff |

**Key message:** "VERITAS OS gives you full control over AI decision-making — execute, audit, and govern — all from a unified interface."

---

## CI Quality Checklist

- [x] Backend: ruff + bandit + pytest (40%+ coverage)
- [x] Frontend: TypeScript strict + ESLint + vitest unit tests
- [x] A11y: axe-core checks on all pages (WCAG 2.0 AA)
- [x] E2E: Playwright smoke tests (console, audit, governance, navigation)
- [x] GitHub Actions: lint → test → frontend → frontend-e2e pipeline
