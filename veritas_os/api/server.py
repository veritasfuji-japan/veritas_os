# veritas/api/server.py
from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY  # noqa: F401

# ---- VERITAS core層 ----
from veritas_os.core import (
    kernel as veritas_core,
    fuji as fuji_core,
    memory as mem,
    value_core,
    world as world_model,
    planner as planner_core,
    llm_client,
    reason as reason_core,
    debate as debate_core,
)
from veritas_os.core.config import cfg
from veritas_os.core.planner import plan_for_veritas_agi
from veritas_os.core.sanitize import mask_pii
from veritas_os.core.memory import predict_decision_status
from veritas_os.core.reason import generate_reason

# ---- ログ／メモリ層 ----
from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
)
from veritas_os.logging.paths import LOG_DIR, DATASET_DIR
from veritas_os.memory.store import MemoryStore

# ---- API層 ----
from veritas_os.api.schemas import (
    DecideRequest,
    DecideResponse,
    FujiDecision,
    ChatRequest,
    ValuesOut,
)
from veritas_os.api.constants import DECISION_ALLOW, DECISION_REJECTED
from veritas_os.api import evolver
from veritas_os.api.evolver import load_persona

OPEN_API_KEY = os.getenv("OPEN_API_KEY", "")

def redact(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '[redacted@email]', text)
    text = re.sub(r'\b\d{2,4}[-・\s]?\d{2,4}[-・\s]?\d{3,4}\b', '[redacted:phone]', text)
    return text

# ---- init ----
REPO_ROOT = Path(__file__).resolve().parents[1]   # .../veritas_os
load_dotenv(REPO_ROOT / ".env")

app = FastAPI(title="VERITAS Public API", version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- storage paths ----
# REPO_ROOT = .../veritas_clean_test2/veritas_os を想定
SCRIPTS_DIR = REPO_ROOT / "scripts"

# ルートの logs ディレクトリ
LOG_ROOT = Path(
    os.getenv("VERITAS_LOG_ROOT", str(SCRIPTS_DIR / "logs"))
).expanduser()
LOG_ROOT.mkdir(parents=True, exist_ok=True)

# trust_log.json / trust_log.jsonl などは logs 直下に置く
LOG_DIR  = LOG_ROOT
LOG_JSON  = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"

# decide_xxx.json など「DASH 用ログ」は logs/DASH/ にまとめる
DASH_DIR = LOG_ROOT / "DASH"
DASH_DIR.mkdir(parents=True, exist_ok=True)

# doctor.py などのシャドウ出力も DASH に寄せたい場合はこうする
SHADOW_DIR = DASH_DIR

# モデルはリポジトリ内 core/models/ に固定
MEMORY_MODEL_PATH = REPO_ROOT / "core" / "models" / "memory_model.pkl"

# データセットも DASH にまとめたいならこちら
DATASET_DIR = DASH_DIR
# （もし別にしたいなら SCRIPTS_DIR / "datasets" などに変更）

# value_stats.json だけはプロジェクト直下 data/ に置く
PROJECT_ROOT = REPO_ROOT.parent            # .../veritas_clean_test2
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VAL_JSON = DATA_DIR / "value_stats.json"

# ディレクトリを実際に作成（念のため）
LOG_DIR.mkdir(parents=True, exist_ok=True)
DASH_DIR.mkdir(parents=True, exist_ok=True)
DATASET_DIR.mkdir(parents=True, exist_ok=True)

# ---- API key ----
API_KEY = (os.getenv("VERITAS_API_KEY") or cfg.api_key or "").strip()
if not API_KEY:
    print("[WARN] VERITAS_API_KEY 未設定（開発時のみ許容）")
api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(x_api_key: str = Security(api_key_scheme)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if not secrets.compare_digest(x_api_key.strip(), API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ---- HMAC signature / replay ----
API_SECRET = (os.getenv("VERITAS_API_SECRET") or "").encode("utf-8")
_NONCE_TTL_SEC = 300
_nonce_store: dict[str, float] = {}

def _cleanup_nonces():
    now = time.time()
    for k, until in list(_nonce_store.items()):
        if now > until:
            _nonce_store.pop(k, None)

def _check_and_register_nonce(nonce: str) -> bool:
    _cleanup_nonces()
    if nonce in _nonce_store:
        return False
    _nonce_store[nonce] = time.time() + _NONCE_TTL_SEC
    return True

async def verify_signature(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    x_nonce: str | None = Header(default=None, alias="X-Nonce"),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
):
    if not API_SECRET:
        raise HTTPException(status_code=500, detail="Server secret missing")
    if not (x_api_key and x_timestamp and x_nonce and x_signature):
        raise HTTPException(status_code=401, detail="Missing auth headers")
    try:
        ts = int(x_timestamp)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid timestamp")
    if abs(int(time.time()) - ts) > _NONCE_TTL_SEC:
        raise HTTPException(status_code=401, detail="Timestamp out of range")
    if not _check_and_register_nonce(x_nonce):
        raise HTTPException(status_code=401, detail="Replay detected")
    body = (await request.body()).decode("utf-8") if (await request.body()) else ""
    payload = f"{ts}\n{x_nonce}\n{body}"
    mac = hmac.new(API_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    if not hmac.compare_digest(mac, (x_signature or "").lower()):
        raise HTTPException(status_code=401, detail="Invalid signature")
    return True

# ---- rate limit（簡易）----
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0
_rate_bucket: dict[str, tuple[int, float]] = {}

def enforce_rate_limit(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    count, start = _rate_bucket.get(x_api_key, (0, time.time()))
    now = time.time()
    if now - start > _RATE_WINDOW:
        _rate_bucket[x_api_key] = (1, now)
        return True
    if count + 1 > _RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_bucket[x_api_key] = (count + 1, start)
    return True

# ---- utils ----
def _to_plain(obj):
    if hasattr(obj, "model_dump"): return obj.model_dump()
    if hasattr(obj, "dict"):       return obj.dict()
    if isinstance(obj, (list, tuple)): return [_to_plain(x) for x in obj]
    if isinstance(obj, dict):          return {k: _to_plain(v) for k,v in obj.items()}
    return obj

async def call_core_decide(core_fn, *, context, query, alternatives, min_evidence):
    params = set(inspect.signature(core_fn).parameters.keys())
    kw: Dict[str, Any] = {}
    ctx = dict(context or {})
    if "query" not in params and query:
        ctx.setdefault("query", query)
        ctx.setdefault("prompt", query)
        ctx.setdefault("text",   query)
    if "ctx" in params:       kw["ctx"] = ctx
    elif "context" in params: kw["context"] = ctx
    if "options" in params:       kw["options"] = alternatives or []
    elif "alternatives" in params: kw["alternatives"] = alternatives or []
    if "min_evidence" in params: kw["min_evidence"] = min_evidence
    elif "k" in params:         kw["k"] = min_evidence
    elif "top_k" in params:     kw["top_k"] = min_evidence
    if "query" in params:       kw["query"] = query

    if inspect.iscoroutinefunction(core_fn):
        return await core_fn(**kw)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: core_fn(**kw))

# ---- 422 の見やすい返却 ----
def _decide_example() -> dict:
    return {
        "context": {"user_id": "demo"},
        "query": "VERITASを進化させるには？",
        "options": [{"title":"最小ステップで前進"}],
        "min_evidence": 1
    }
@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    raw = (await request.body()).decode("utf-8", "replace") if (await request.body()) else ""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "hint": {"expected_example": _decide_example()},
            "raw_body": raw
        }
    )

# ---- health / status ----
@app.get("/health")
@app.get("/v1/health")
def health():
    return {"ok": True, "uptime": int(time.time() - START_TS)}

@app.get("/status")
@app.get("/v1/status")
@app.get("/api/status")
def status():
    return {"ok": True, "version": "veritas-api 1.0.1", "uptime": int(time.time() - START_TS)}

# ---- trust log helpers ----
def _load_logs_json() -> list:
    try:
        with open(LOG_JSON, "r", encoding="utf-8") as f:
            return json.load(f).get("items", [])
    except Exception:
        return []

def _save_json(items: list) -> None:
    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)

def append_trust_log(entry: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    items = _load_logs_json()
    items.append(entry)
    _save_json(items)

def write_shadow_decide(request_id: str, body: dict, chosen: dict, telos_score: float, fuji: dict) -> None:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = SHADOW_DIR / f"decide_{ts}.json"
    rec = {
        "request_id": request_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "query": (body.get("query") or (body.get("context") or {}).get("query") or ""),
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": (fuji or {}).get("status")
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)

# ---- main: /v1/decide ----
@app.post("/v1/decide", response_model=DecideResponse, dependencies=[Depends(require_api_key)])
async def decide(req: DecideRequest, request: Request):
    started_at = time.time()
    body = req.model_dump()

    # ---------- SAFE INIT ----------
    raw: Dict[str, Any] = {}
    evidence:  List[Any] = []
    critique:  List[Any] = []
    debate:    List[Any] = []
    telos:     float     = 0.0
    fuji_dict: Dict[str, Any] = {}
    alternatives: List[Dict[str, Any]] = []
    chosen: Dict[str, Any] = {}
    extras_payload: Dict[str, Any] = {"safe_instructions": [], "redactions": [], "masked_example": None}
    modifications: List[Any] = []
    response_extras: Dict[str, Any] = {"metrics": {}}

    # ---------- Query / Context / user_id ----------
    context = body.get("context") or {}
    raw_query = body.get("query") or context.get("query") or ""
    if not isinstance(raw_query, str):
        raw_query = str(raw_query)
    query = raw_query.strip()
    user_id = context.get("user_id") or body.get("user_id") or "anon"

    try:
        context = world_model.inject_state_into_context(context, user_id)
    except Exception as e:
        print("[WorldOS] inject_state_into_context skipped:", e)

    # VERITAS / AGI 系クエリ判定
    qlower = query.lower()
    is_veritas_query = any(
        k in qlower for k in ["veritas", "agi", "protoagi", "プロトagi", "veritasのagi化"]
    )

    # ---------- PlannerOS: AGI/VERITAS 用の計画生成 ----------
    plan: Dict[str, Any] = {"steps": [], "source": "fallback"}
    if is_veritas_query:
        try:
            from core.planner import plan_for_veritas_agi

            plan = plan_for_veritas_agi(
                context=context,
                query=query,
            )
            response_extras.setdefault("planner", plan)
            print(f"[PlannerOS:AGI] steps={len(plan.get('steps', []))}")
        except Exception as e:
            print("[PlannerOS:AGI] skipped:", e)

    # ---------- MemoryOS: prior 取り込み ----------
    recent_logs = mem.recent(user_id, limit=20)
    similar = [
        r for r in recent_logs
        if query and query[:8] in str(((r.get("value") or {}).get("query") or ""))
    ]
    prior_scores: Dict[str, float] = {}
    for r in similar:
        c = (r.get("value") or {}).get("chosen") or {}
        t = c.get("title") or c.get("id")
        if t:
            prior_scores[t] = prior_scores.get(t, 0.0) + 1.0

    # ---------- basics ----------
    request_id = body.get("request_id") or secrets.token_hex(16)
    min_ev     = int(body.get("min_evidence") or 1)

    # ---------- Memory retrieval + usage logging ----------
    mem_hits: Dict[str, List[Dict[str, Any]]] = {}
    retrieved: List[Dict[str, Any]] = []
    try:
        if query:
            # しきい値を 0.0 まで下げて、とにかく top-k を拾う
            mem_hits = MEM.search(
                query,
                k=6,
                kinds=["semantic", "skills", "episodic"],
                min_sim=0.0,
            )

        # mem_hits: {kind: [ {id,text,tags,meta,score}, ... ], ... } を flatten
        for kind, hits in (mem_hits or {}).items():
            if not isinstance(hits, list):
                continue
            for h in hits:
                if not isinstance(h, dict):
                    continue
                h2 = dict(h)
                h2.setdefault("kind", kind)
                retrieved.append(h2)

        # metrics
        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["mem_hits"] = len(retrieved)

        # evidence（上位3件を採用）
        for r in retrieved[:3]:
            evidence.append({
                "source": f"memory:{r.get('kind','')}",
                "uri": (r.get("meta") or {}).get("uri") or r.get("id"),
                "snippet": (
                    r.get("text")
                    or (r.get("value") or {}).get("text")
                    or (r.get("value") or {}).get("query")
                    or str(r)[:200]
                ),
                "confidence": float(r.get("score", 0.6)),
            })

        # Doctor Dashboard 用 usage log
        if retrieved:
            cited_ids: List[str] = []
            for r in retrieved[:3]:
                cid = r.get("id") or (r.get("meta") or {}).get("uri")
                if cid:
                    cited_ids.append(str(cid))

            if cited_ids:
                ts = datetime.utcnow().isoformat() + "Z"
                mem.put(
                    user_id,
                    key=f"memory_use_{ts}",
                    value={
                        "used": True,
                        "query": query,
                        "citations": cited_ids,
                        "timestamp": ts,
                    },
                )
                mem.add_usage(user_id, cited_ids)
                print(f"[MemoryOS] usage logged: {len(cited_ids)} citations")

        print(f"[AGI-Retrieval] Added memory evidences: {len(retrieved)}")

    except Exception as e:
        print("[MemoryOS] search skipped:", e)
        mem_hits = {}
        retrieved = []
        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["mem_hits"] = 0

    # ---------- options 正規化 ----------
    def _to_dict(o: Any) -> Dict[str, Any]:
        if isinstance(o, dict): return o
        if hasattr(o, "model_dump"): return o.model_dump(exclude_none=True)
        if hasattr(o, "dict"):       return o.dict()
        return {}

    def _to_float_or(v, default: float) -> float:
        if v in (None, "", "null", "None"):
            return default
        try:
            return float(v)
        except Exception:
            return default

    def _norm_alt(o: Any) -> Dict[str, Any]:
        d = _to_dict(o) or {}
        if "title" not in d and "text" in d:
            d["title"] = d.pop("text")
        d.setdefault("title", "")
        d["description"] = (d.get("description") or d.get("text") or "")
        d["score"]     = _to_float_or(d.get("score", 1.0), 1.0)
        d["score_raw"] = _to_float_or(d.get("score_raw", d["score"]), d["score"])
        d["id"] = str(d.get("id") or uuid4().hex)
        return d

    input_alts = body.get("options") or body.get("alternatives") or []
    if not isinstance(input_alts, list):
        input_alts = []
    input_alts = [_norm_alt(a) for a in input_alts]

    # ---------- VERITAS / AGI クエリ向けのドメイン特化 alternatives ----------
    if not input_alts and is_veritas_query:
        step_alts: List[Dict[str, Any]] = []

        # 1) Planner の step から候補を生成
        for i, st in enumerate(plan.get("steps") or [], 1):
            title = st.get("title") or st.get("name") or f"Step {i}"
            detail = (
                st.get("detail")
                or st.get("description")
                or st.get("why")
                or ""
            )
            step_alts.append(
                _norm_alt(
                    {
                        "id": st.get("id") or f"plan_step_{i}",
                        "title": title,
                        "description": detail,
                        "score": 1.0,
                        "meta": {"source": "planner", "step_index": i},
                    }
                )
            )

        # 2) planner から取れなければ、ハードコード fallback
        if step_alts:
            input_alts = step_alts
        else:
            input_alts = [
                _norm_alt(
                    {
                        "id": "veritas_mvp_demo",
                        "title": "MVPデモを最短で見せられる形にする",
                        "description": "Swagger/CLI で実際に /v1/decide を叩きながら説明できる30〜60秒のデモを作る。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_report",
                        "title": "技術監査レポートを仕上げる",
                        "description": "VERITAS 技術監査レポートを第三者が読めるレベルにブラッシュアップする。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_spec_sheet",
                        "title": "MVP仕様書を1枚にまとめる",
                        "description": "CLI/API・FUJI・DebateOS・MemoryOS の流れを1枚の図＋テキストに整理する。",
                    }
                ),
                _norm_alt(
                    {
                        "id": "veritas_demo_script",
                        "title": "第三者向けデモ台本を作る",
                        "description": "どの順番で画面を見せ、何を喋るかのシナリオを作成する。",
                    }
                ),
            ]

    # （以下、元のロジックをそのまま継続）
    # 過去傾向でスコア微調整（最大+5%）
    if prior_scores:
        max_prior = max(prior_scores.values())
        if max_prior > 0:
            for d in input_alts:
                title = d.get("title") or d.get("id")
                boost = prior_scores.get(title, 0.0) / max_prior
                d["score_raw"] = d.get("score_raw", d.get("score", 1.0))
                d["score"] = float(d.get("score", 1.0)) * (1.0 + 0.05*boost)

    # ---------- 過去の Plan を alternatives に注入（任意） ----------
    try:
        plan_alts = []
        for r in recent_logs:
            v = r.get("value") or {}
            if v.get("kind") != "plan":
                continue
            if query and query[:10] not in str(v.get("query") or ""):
                # ざっくり同じテーマだけ使う
                continue

            p = v.get("planner") or {}
            steps = p.get("steps") or []
            if not steps:
                continue

            # 一番最初のステップをタイトルにする例
            first = steps[0]
            step_title = first.get("title") or first.get("name") or "過去プランの継続"

            alt = _norm_alt({
                "title": f"過去プランを継続: {step_title}",
                "description": f"以前の決定ログのplanを引き継ぐ: {v.get('query')}",
                "score": 0.8,  # ちょい高めのベース
                "meta": {
                    "source": "plan",
                    "origin_query": v.get("query"),
                },
            })
            plan_alts.append(alt)

        # ユーザーが options を送っていない場合だけ、過去プランを候補に混ぜる
        if plan_alts and not input_alts:
            input_alts = plan_alts

    except Exception as e:
        print("[MemoryOS] plan→alternatives skipped:", e)

    # --- C: episodic メモリから「過去の決定案」を alternatives に注入 ---
    try:
        mem_alts: List[Dict[str, Any]] = []

        # 1) episodic メモリだけ抽出
        episodic_hits = [
            r for r in (retrieved or [])
            if isinstance(r, dict) and r.get("kind") == "episodic"
        ]

        # 2) メモリからタイトルなど抽出
        for h in episodic_hits:
            txt = (h.get("text") or "").strip()
            if not txt:
                continue

            title = ""

            # ① [chosen] フォーマットを優先
            if "[chosen]" in txt:
                try:
                    _, tail = txt.split("[chosen]", 1)
                    title = tail.split("\n", 1)[0].strip(" :　")
                except Exception:
                    pass

            # ② 旧フォーマット "chosen:" にも対応
            if not title and "chosen:" in txt:
                try:
                    _, tail = txt.split("chosen:", 1)
                    title = tail.split("|", 1)[0].strip()
                except Exception:
                    pass

            # ③ それでも取れない or "None" だけになっている時は先頭40文字
            if (not title) or (title.strip().lower() == "none"):
                title = txt[:40]

            alt = _norm_alt({
                "title": title,
                "description": f"過去の決定ログから復元: {title}",
                "score": float(h.get("score", 0.8)),
                "meta": {
                    "source": "episodic",
                    "memory_id": h.get("id"),
                },
            })
            mem_alts.append(alt)

        # episodic 由来 alternatives を末尾に追加
        if mem_alts:
            input_alts.extend(mem_alts)

    except Exception as e:
        print("[episodic] alternative generation failed:", e)

    # ---------- core 呼び出し ----------
    try:
        raw = await call_core_decide(
            core_fn=veritas_core.decide,
            context=context, query=query,
            alternatives=input_alts, min_evidence=min_ev
        )
    except Exception as e:
        print("[decide] core error:", e)

    # ---------- 吸収（安全） ----------
    if isinstance(raw, dict) and raw:
        raw_evi = raw.get("evidence")
        if isinstance(raw_evi, list):
            evidence.extend(raw_evi)

        critique = raw.get("critique") or critique
        debate   = raw.get("debate")   or debate
        telos    = float(raw.get("telos_score") or telos)
        fuji_dict = raw.get("fuji") or fuji_dict

        alts_from_core = raw.get("alternatives") or raw.get("options") or []
        if isinstance(alts_from_core, list):
            alternatives = [_norm_alt(a) for a in alts_from_core]

        if isinstance(raw.get("extras"), dict):
            extras_payload.update(raw["extras"])

    # fallback alternatives
    alts = alternatives
    if not alts:
        alts = [
            _norm_alt({"title": "最小ステップで前進する"}),
            _norm_alt({"title": "情報収集を優先する"}),
            _norm_alt({"title": "今日は休息に充てる"}),
        ]
    alts = veritas_core._dedupe_alts(alts)

    # --- worldmodel -------------------------------
    try:
        boosted = []
        for d in alts:
            sim = world_model.simulate(d, context)
            d["world"] = sim
            # utilityとconfidenceで最大+3%の上振れ
            micro = max(0.0, min(0.03, 0.02 * sim.get("utility", 0.0) + 0.01 * sim.get("confidence", 0.5)))
            d["score"] = float(d.get("score", 1.0)) * (1.0 + micro)
            boosted.append(d)
        alts = boosted
    except Exception as e:
        print("[WorldModelOS] skip:", e)

    # --- MemoryModel score boost (before choose) -------------------------------
    def allow_prob(text: str) -> float:
        d = predict_gate_label(text)
        return float(d.get("allow", 0.0))

    # MODEL_FILE に依存しないように安全にパスを取得
    def _mem_model_path() -> str:
        try:
            from veritas_os.core import memory_model as mm
            if hasattr(mm, "MODEL_FILE"):
                return str(mm.MODEL_FILE)
            if hasattr(mm, "MODEL_PATH"):
                return str(mm.MODEL_PATH)
        except Exception:
            pass
        return ""

    try:
        response_extras.setdefault("metrics", {})
        if MEM_VEC and MEM_CLF:
            response_extras["metrics"]["mem_model"] = {
                "applied": True,
                "reason": "loaded",
                "path": _mem_model_path(),
                "classes": getattr(MEM_CLF, "classes_", []).tolist()
                            if hasattr(MEM_CLF, "classes_") else None
            }

            # 各オプションの score を微調整（最大 +10%）
            for d in alts:
                text = (d.get("title") or "") + " " + (d.get("description") or "")
                p_allow = allow_prob(text)
                base = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", base))
                d["score"] = base * (1.0 + 0.10 * p_allow)  # allowが高いほど上げる
        else:
            response_extras["metrics"]["mem_model"] = {
                "applied": False,
                "reason": "model_not_loaded",
                "path": _mem_model_path(),
            }
    except Exception as e:
        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["mem_model"] = {
            "applied": False, "error": str(e), "path": _mem_model_path()
        }

    # --- world.utility / score を使って chosen を決定 ---
    chosen = raw.get("chosen") if isinstance(raw, dict) else {}
    if not isinstance(chosen, dict) or not chosen:
        try:
            def _choice_key(d: Dict[str, Any]) -> float:
                # world.utility があればそれを最優先、それが無ければ score
                w = (d.get("world") or {}).get("utility")
                try:
                    return float(w)
                except Exception:
                    return float(d.get("score", 1.0))

            chosen = max(alts, key=_choice_key)
        except Exception:
            chosen = alts[0] if alts else {}

    # ===== DebateOS: LLM ベースの批判・代替案生成 =====
    try:
        # LLM で chosen が妥当か検討
        debate_res = debate_core.run_debate(
            context=context,
            query=query,
            chosen=chosen,
            alts=alts,
        )

        # extras に丸ごと入れる
        response_extras.setdefault("debate", debate_res)

        # 互換用: 既存の top-level "debate" フィールドにも要約だけ入れておく
        debate = [{
            "summary": debate_res.get("summary"),
            "risk_delta": debate_res.get("risk_delta"),
            "suggested_choice_id": debate_res.get("suggested_choice_id"),
            "source": debate_res.get("source", "openai_llm"),
        }]

        # 別の案を推してきたら chosen を差し替え
        sug_id = debate_res.get("suggested_choice_id")
        if sug_id:
            for cand in alts:
                if str(cand.get("id")) == str(sug_id):
                    chosen = cand
                    break

    except Exception as e:
        print("[DebateOS] skipped:", e)

    # ---------- FUJI 事前チェック ----------
    try:
        fuji_pre = fuji_core.validate_action(query, context)
    except Exception as e:
        print("[fuji] error:", e)
        fuji_pre = {"status": "allow", "reasons": [], "violations": [], "risk": 0.0}

    status_map = {"ok": "allow", "allow": "allow", "pass": "allow",
                  "modify": "modify", "block": "rejected", "deny": "rejected", "rejected": "rejected"}
    fuji_pre["status"] = status_map.get((fuji_pre.get("status") or "allow").lower(), "allow")
    fuji_dict = {**(fuji_dict if isinstance(fuji_dict, dict) else {}), **fuji_pre}

    # FUJI 事前判定を Evidence に刻む
    fuji_status = fuji_dict.get("status", "allow")
    risk_val    = float(fuji_dict.get("risk", 0.0))
    reasons     = fuji_dict.get("reasons", []) or []
    viols       = fuji_dict.get("violations", []) or []
    evidence.append({
        "source": "internal:fuji",
        "uri": None,
        "snippet": f"[FUJI pre] status={fuji_status}, risk={risk_val}, "
                   f"reasons={'; '.join(reasons) if reasons else '-'}, "
                   f"violations={', '.join(viols) if viols else '-'}",
        "confidence": 0.9 if fuji_status in ("modify", "rejected") else 0.8,
    })

    # ---------- ValueCore 評価 ----------
    try:
        vc = value_core.evaluate(query, context or {})
        values_payload = {
            "scores": vc.scores,
            "total": vc.total,
            "top_factors": vc.top_factors,
            "rationale": vc.rationale,
        }
    except Exception as e:
        print("[value_core] evaluation error:", e)
        values_payload = {"scores": {}, "total": 0.0, "top_factors": [], "rationale": "evaluation failed"}

    # ---- EMA を読み取り（なければ 0.5）----
    value_ema = 0.5
    try:
        if VAL_JSON.exists():
            vs = json.load(open(VAL_JSON, encoding="utf-8"))
            value_ema = float(vs.get("ema", 0.5))
    except Exception as e:
        print("[value_ema] load skipped:", e)

    # input_alts / alts のいずれにも軽いブースト
    BOOST_MAX = float(os.getenv("VERITAS_VALUE_BOOST_MAX", "0.05"))  # 上限5%
    boost = (value_ema - 0.5) * 2.0  # -1..+1
    boost = max(-1.0, min(1.0, boost)) * BOOST_MAX

    def _apply_boost(arr):
        out = []
        for d in arr:
            try:
                s = float(d.get("score", 1.0))
                d["score_raw"] = float(d.get("score_raw", s))
                d["score"] = max(0.0, s * (1.0 + boost))
            except Exception:
                pass
            out.append(d)
        return out

    input_alts = _apply_boost(input_alts)
    alts = _apply_boost(alts)

    # FUJIが出した risk を EMA で微調整（±15% まで）
    RISK_EMA_WEIGHT = float(os.getenv("VERITAS_RISK_EMA_WEIGHT", "0.15"))
    effective_risk = float(fuji_dict.get("risk", 0.0)) * (1.0 - RISK_EMA_WEIGHT * value_ema)
    effective_risk = max(0.0, min(1.0, effective_risk))

    BASE_TELOS_TH = 0.55
    TELOS_EMA_DELTA = float(os.getenv("VERITAS_TELOS_EMA_DELTA", "0.10"))  # 最大0.10下げる
    telos_threshold = BASE_TELOS_TH - TELOS_EMA_DELTA * (value_ema - 0.5) * 2.0  # 0.45〜0.65
    telos_threshold = max(0.35, min(0.75, telos_threshold))

    # ---- world.utility: 実利スコア生成（Doctor/AGIメトリクス用） ----
    try:
        def _clip01(x: float) -> float:
            try:
                return max(0.0, min(1.0, float(x)))
            except Exception:
                return 0.0

        # ValueCore の合計スコア（0〜1）
        v_total = _clip01(values_payload.get("total", 0.5))
        # Telos とリスク（0〜1）
        t = _clip01(telos)
        r = _clip01(effective_risk)

        # alternatives（alts）それぞれに utility を付与
        for d in alts:
            base = _clip01(d.get("score", 0.0))

            util = base
            # 「価値が高いほど↑」
            util *= (0.5 + 0.5 * v_total)
            # 「リスクが高いほど↓」
            util *= (1.0 - r)
            # 「telos が高いほど↑」
            util *= (0.5 + 0.5 * t)

            util = _clip01(util)

            d.setdefault("world", {})
            d["world"]["utility"] = util

        # ざっくり平均値を metrics にも載せておく（おまけ）
        if alts:
            avg_u = sum((d.get("world") or {}).get("utility", 0.0) for d in alts) / len(alts)
        else:
            avg_u = 0.0

        response_extras.setdefault("metrics", {})
        response_extras["metrics"]["avg_world_utility"] = round(float(avg_u), 4)

    except Exception as e:
        print("[world.utility] skipped:", e)

    # ---------- gate 決定 ----------
    risk = float(fuji_dict.get("risk", 0.0))
    decision_status, rejection_reason = "allow", None
    modifications = fuji_dict.get("modifications") or []

    # ----- DebateOS の risk_delta を統合 -----
    try:
        if isinstance(debate, list) and debate:
            deb = debate[0]  # 1つだけ採用（最も新しい）
            delta = float(deb.get("risk_delta", 0.0))

            # FUJI の risk へ加算（-0.5〜+0.5 を許容）
            new_risk = risk + delta
            new_risk = max(0.0, min(1.0, new_risk))  # 0〜1 にクリップ

            print(f"[Debate→FUJI] risk {risk:.3f} → {new_risk:.3f} (delta={delta:+.3f})")
            risk = new_risk

    except Exception as e:
        print("[Debate→FUJI] merge failed:", e)

    # --- 🔁 FUJI×ValueCore 相互参照（WorldModelOS連携） ---
    try:
        # 世界予測(world)があれば “危険寄り”をやや強調（最大 +0.05）
        if alts:
            topw = max(alts, key=lambda d: float(d.get("score", 1.0))).get("world", {})
            utility = float(topw.get("utility", 0.0))
            conf    = float(topw.get("confidence", 0.5))
            penalty = max(0.0, -utility) * 0.05 * conf
            effective_risk = max(0.0, min(1.0, risk + penalty))
            print(f"[RiskTune] effective_risk tuned → {effective_risk:.3f}")
    except Exception as e:
        print("[RiskTune] skip:", e)

    # 既存の gate 決定ロジック
    decision_status, rejection_reason, modifications = "allow", None, []
    if fuji_dict.get("status") == "modify":
        modifications = fuji_dict.get("modifications") or []
    elif fuji_dict.get("status") == "rejected":
        decision_status = "rejected"
        rejection_reason = "FUJI gate: " + ", ".join(fuji_dict.get("reasons", []) or ["policy_violation"])
        chosen, alts = {}, []
    elif effective_risk >= 0.90 and telos < telos_threshold:
        decision_status = "rejected"
        rejection_reason = f"FUJI gate: high risk ({effective_risk:.2f}) & low telos (<{telos_threshold:.2f})"
        chosen, alts = {}, []

    # --- Value learning: store running stats + history ---
    def _load_valstats():
        try:
            with open(VAL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"ema": 0.5, "alpha": 0.2, "n": 0, "history": []}

    def _save_valstats(d):
        with open(VAL_JSON, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    try:
        valstats = _load_valstats()
        alpha = float(valstats.get("alpha", 0.2))
        ema_prev = float(valstats.get("ema", 0.5))
        n_prev = int(valstats.get("n", 0))
        v = float(values_payload.get("total", 0.5))  # 0..1

        ema_new = (1.0 - alpha) * ema_prev + alpha * v
        hist = valstats.get("history", [])
        hist.append({"ts": datetime.utcnow().isoformat()+"Z", "ema": ema_new, "value": v})
        # ヒストリを肥大化させない（最新1000件に丸め）
        hist = hist[-1000:]

        valstats.update({"ema": ema_new, "n": n_prev + 1, "last": v, "history": hist})
        _save_valstats(valstats)

        # レスポンスで見えるように
        values_payload["ema"] = round(ema_new, 4)

    except Exception as e:
        print("[value-learning] skip:", e)

    # ----- extras -----
    # 既存の raw 側の extras を安全に引き継ぎ（res はまだ作らない！）
    try:
        prev_extras = dict(((raw or {}).get("extras") or {}))
    except Exception:
        prev_extras = {}

    try:
        response_extras = {
            **prev_extras,
            "metrics": {
                **(prev_extras.get("metrics") or {}),
                "alts_count": len(alts),
                "has_evidence": bool(evidence),
                "value_ema": round(value_ema, 4),
                "effective_risk": round(effective_risk, 4),
                "telos_threshold": round(telos_threshold, 3),
            },
        }
    except Exception:
        response_extras = {
            "metrics": {
                "alts_count": len(alts),
                "has_evidence": bool(evidence),
            }
        }

    # PlannerOS の結果を extras に格納
    try:
        response_extras["planner"] = plan
    except Exception as e:
        print("[PlannerOS] extras attach skipped:", e)

    # ----- metrics 追記: latency_ms / mem_evidence_count -----
    try:
        # 応答時間（ms）
        duration_ms = int((time.time() - started_at) * 1000)

        # evidence のうち "memory" 系ソースの件数を数える
        mem_evi_cnt = 0
        for ev in (evidence or []):
            src = str(ev.get("source", "") or "")
            if src.startswith("memory"):
                mem_evi_cnt += 1

        response_extras.setdefault("metrics", {})
        response_extras["metrics"].update(
            {
                "latency_ms": duration_ms,
                "mem_evidence_count": mem_evi_cnt,
            }
        )
    except Exception as e:
        print("[metrics] latency/memory_evidence skipped:", e)

    # ============================
    # MemoryOS retrieval (メタ情報だけ)
    # ============================
    try:
        mem_result = {
            "query": query,
            "context": context,  # raw ではなく context を渡す方が自然
            "user_id": (context or {}).get("user_id", "unknown"),
            # ここで実際の検索はしていない（将来拡張用のプレースホルダ）
            "memories": [],
            "used_count": 0,
        }
    except Exception as e:
        print("[MemoryOS ERROR]", e)
        mem_result = {}

    # --- Memory 引用メタデータ付与（extras に格納）---
    if isinstance(mem_result, dict):
        response_extras["memory_citations"] = mem_result.get("memories", [])
        response_extras["memory_used_count"] = mem_result.get("used_count", 0)
    else:
        response_extras["memory_citations"] = []
        response_extras["memory_used_count"] = 0

    # ---------- Episodic Memory logging (per /v1/decide call) ----------
    try:
        # どのユーザーか
        uid = (context or {}).get("user_id") or user_id or "anon"

        # 1本のテキストに「質問」「選択された案」「FUJI/ValueCore」などをまとめる
        episode_text = "\n".join([
            f"[query] {query}",
            f"[chosen] { (chosen or {}).get('title') or str(chosen) }",
            f"[decision_status] {decision_status}",
            f"[risk] {float(fuji_dict.get('risk', 0.0)):.3f}",
        ])

        MEM.put_episode(
            text=episode_text,
            tags=["episode", "decide", "veritas"],
            meta={
                "user_id": uid,
                "request_id": request_id,
                "ts": datetime.utcnow().isoformat() + "Z",
            },
        )
        print(f"[MemoryOS] episodic saved for {uid}")
    except Exception as e:
        print("[MemoryOS] episodic save failed:", e)

    # ---------- レスポンス ----------
    res = {
        "request_id": request_id,
        "chosen": chosen,
        "alternatives": alts,
        "options": list(alts),
        "evidence": evidence,
        "critique": critique,
        "debate": debate,
        "telos_score": telos,
        "fuji": fuji_dict,
        "rsi_note": raw.get("rsi_note") if isinstance(raw, dict) else None,
        "extras": response_extras,
        "gate": {
            "risk": effective_risk,
            "telos_score": telos,
            "decision_status": decision_status,
            "reason": rejection_reason,
            "modifications": modifications,
        },
        "values": values_payload,
        "persona": load_persona(),
        "version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
        "evo": raw.get("evo") if isinstance(raw, dict) else None,
        "decision_status": decision_status,
        "rejection_reason": rejection_reason,
        "memory_citations": response_extras.get("memory_citations", []),
        "memory_used_count": response_extras.get("memory_used_count", 0),
        "plan": plan,
        "planner": response_extras.get("planner", plan),
    }

    # ---------- 監査ログ ----------
    try:
        append_trust_log({
            "request_id": request_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "context": context, "query": query,
            "chosen": chosen, "telos_score": telos,
            "fuji": fuji_dict, "sha256_prev": None,
        })
        write_shadow_decide(request_id, body, chosen, telos, fuji_dict)
    except Exception as e:
        print("[audit] log write skipped:", e)

    # ---------- 型保証 ----------
    try:
        payload = DecideResponse.model_validate(res).model_dump()
    except Exception as e:
        print("[model] decide response coerce:", e)
        payload = res
    # --- 型保証のtry/except後に payload が確定している前提 ---

    # 反省 (ReasonOS)
    try:
        # ① いつもの reflection（ローカル評価）
        reflection = reason_core.reflect({
            "query":  query,
            "chosen": payload.get("chosen", {}),
            "gate":   payload.get("gate", {}),
            "values": payload.get("values", {}),
        })

        # ② 反省の “数値ブースト” を ValueCore EMA に微加算 (±0.1レンジ)
        vs_path = VAL_JSON          # あなたの既存パス（~/veritas/value_stats.json）
        valstats = {}
        if vs_path.exists():
            valstats = json.load(open(vs_path, encoding="utf-8"))
        ema = float(valstats.get("ema", 0.5))
        ema = max(0.0, min(1.0, ema + float(reflection.get("next_value_boost", 0.0))))
        valstats["ema"] = round(ema, 4)
        json.dump(valstats, open(vs_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

        # ③ OpenAI LLM で “自然文の反省” を生成（失敗時は reflection を fallback）
        try:
            payload["reason"] = generate_reason(
                query=query,
                planner=payload.get("planner") or payload.get("plan"),
                values=payload.get("values"),
                gate=payload.get("gate"),
                context=context,
            )
        except Exception as e2:
            print("[ReasonOS] LLM reason failed:", e2)
            payload["reason"] = reflection

    except Exception as e:
        # 上の reflection 自体が失敗したときの最終フォールバック
        print("[ReasonOS] final fallback failed:", e)
        payload["reason"] = {"note": "reflection/LLM both failed"}

    # ---------- Planner → MemoryOS 保存 ----------
    try:
        uid = (context or {}).get("user_id") or user_id or "anon"
        extras = payload.get("extras") or {}
        planner_dict = extras.get("planner") or {}

        if planner_dict:
            # 1) KVS メモリ（時系列ログ）
            mem.put(
                uid,
                key=f"plan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                value={
                    "kind": "plan",
                    "query": query,
                    "chosen": payload.get("chosen"),
                    "planner": planner_dict,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                },
            )

            # 2) ベクトルメモリ（検索用）
            #    steps のタイトルだけざっくり 1 本のテキストにまとめる
            steps = planner_dict.get("steps") or []
            step_lines = []
            for i, st in enumerate(steps, 1):
                title = st.get("title") or st.get("name") or f"Step {i}"
                step_lines.append(f"{i}. {title}")
            plan_text = "\n".join(step_lines)

            MEM.put_episode(
                text=f"[plan] {query}\n{plan_text}",
                tags=["plan", "veritas", "decide"],
                meta={
                    "user_id": uid,
                    "request_id": request_id,
                    "kind": "plan",
                    "ts": datetime.utcnow().isoformat() + "Z",
                },
            )
            print(f"[MemoryOS] plan saved for {uid} (steps={len(steps)})")
        else:
            print("[MemoryOS] no planner in extras; skip plan save")

    except Exception as e:
        print("[MemoryOS] plan save failed:", e)

    # ---------- データセット ----------
    try:
        meta = {
            "session_id": (context or {}).get("user_id") or "anon",
            "request_id": request_id,
            "model": "gpt-5-thinking",
            "api_version": os.getenv("VERITAS_API_VERSION", "veritas-api 1.x"),
            "kernel_version": os.getenv("VERITAS_KERNEL_VERSION", "core-kernel 0.x"),
            "git_commit": os.getenv("VERITAS_GIT_COMMIT"),
            "latency_ms": int((time.time() - started_at) * 1000),
        }
        eval_meta = {"task_type": "decision", "policy_tags": ["no_harm", "privacy_ok"], "rater": {"type": "ai", "id": "telos-proxy"}}
        append_dataset_record(build_dataset_record(req_payload=body, res_payload=payload, meta=meta, eval_meta=eval_meta))
    except Exception as e:
        print("[dataset] skip:", e)

    # ---------- MemoryOS 自動記録 ----------
    try:
        uid = (context or {}).get("user_id", "anon")
        mem.put(
            uid,
            key=f"decision_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            value={
                "query": query,
                "chosen": chosen,
                "values_total": float(payload.get("values", {}).get("total", 0.0)),
                "gate_risk": float(payload.get("gate", {}).get("risk", 0.0)),
                "decision_status": payload.get("decision_status"),
                "telos_score": float(payload.get("telos_score", 0.0)),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )
        print(f"[MemoryOS] saved decision for {uid}")
    except Exception as e:
        print("[MemoryOS] failed to save:", e)

    try:
        MEM.put("episodic", {
            "text": f"query:{query} | chosen:{chosen.get('title')} | telos:{telos:.2f} | risk:{risk:.2f}",
            "tags": ["decide_log"],
            "meta": {"values": values_payload, "fuji": fuji_dict}
        })
    except Exception as e:
        print("[MemoryOS] put failed:", e)
        try:
            mem.put(
                user_id,
                key=f"dialog_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                value={
                    "query": query,
                    "alternatives": alts,
                    "chosen": chosen,
                    "values": values_payload,
                    "evidence": evidence[-5:],
                    "timestamp": datetime.utcnow().isoformat()+"Z"
                }
            )
            value_core.rebalance_from_trust_log()
        except Exception as e2:
            print("[MemoryOS] fallback dialog save failed:", e2)

    # ---------- 決定レコードを LOG/DATASET に保存（学習用に統一） ----------
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        DATASET_DIR.mkdir(parents=True, exist_ok=True)

        metrics = (response_extras.get("metrics") or {})
        latency_ms = int(metrics.get("latency_ms", 0))
        mem_evidence_count = int(metrics.get("mem_evidence_count", 0))

        # 1) evidence リストを安全に拾う
        #    - payload.evidence があれば優先
        #    - なければ decide() 内で使っていた local 変数 evidence を fallback
        evidence_list = []
        if isinstance(payload.get("evidence"), list):
            evidence_list = payload["evidence"]
        elif "evidence" in locals() and isinstance(evidence, list):
            evidence_list = evidence

        # 2) memory 由来 evidence をカウント
        mem_evidence_count = 0
        for ev in evidence_list:
            if not isinstance(ev, dict):
                continue
            src = str(ev.get("source", "")).lower()
            # internal:memory, episodic, semantic, skills など全部拾う
            if (
                "memory" in src
                or "episodic" in src
                or "semantic" in src
                or "skills" in src
            ):
                mem_evidence_count += 1

        # 3) chosen が MemoryOS から来ている場合も 1 件としてカウント保証
        if isinstance(chosen, dict):
            src = str(chosen.get("source", "")).lower()
            if (
                "memory" in src
                or "episodic" in src
                or "semantic" in src
                or "skills" in src
            ):
                # evidence_list が空でも「少なくとも 1 件」はあったことにする
                mem_evidence_count = max(mem_evidence_count, 1)

        # おまけ：metaにも入れておく（将来拡張用）
        meta_payload = payload.get("meta") or {}
        meta_payload["memory_evidence_count"] = mem_evidence_count
        payload["meta"] = meta_payload

        # 保存用の最小統一レコード
        persist = {
            "request_id": request_id,
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "query": query,
            "chosen": chosen,
            "decision_status": payload.get("decision_status") or "unknown",
            "telos_score": float(payload.get("telos_score", 0.0)),
            "gate_risk": float(payload.get("gate", 0.0).get("risk", 0.0)) if isinstance(payload.get("gate"), dict) else 0.0,
            "fuji": (payload.get("fuji") or {}).get("status"),
            "latency_ms": latency_ms,
            "evidence": evidence_list[-5:] if evidence_list else [],
            "memory_evidence_count": mem_evidence_count,
        }

        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fname = f"decide_{stamp}.json"

        # 人が読む用（整形）
        (LOG_DIR / fname).write_text(
            json.dumps(persist, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 学習用（軽量）
        (DATASET_DIR / fname).write_text(
            json.dumps(persist, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print("[persist] decide record skipped:", e)

    # ======== ★ WorldState 更新（最新版） ========
    try:
        uid = (context or {}).get("user_id") or user_id or "anon"

        extras = payload.get("extras") or {}
        planner_obj = extras.get("planner") or extras.get("plan") or None
        latency_ms = (extras.get("metrics") or {}).get("latency_ms")

        world_model.update_from_decision(
            user_id=uid,
            query=payload.get("query") or query,
            chosen=payload.get("chosen") or {},
            gate=payload.get("gate") or {},
            values=payload.get("values") or {},
            planner=planner_obj if isinstance(planner_obj, dict) else None,
            latency_ms=int(latency_ms) if isinstance(latency_ms, (int, float)) else None,
        )
        print(f"[WorldModel] state updated for {uid}")
    except Exception as e:
        print("[WorldModel] update_from_decision skipped:", e)

    # ---------- AGIヒント（VERITAS_AGI用） ----------
    try:
        agi_info = world_model.next_hint_for_veritas_agi()
        extras2 = payload.setdefault("extras", {})
        extras2["veritas_agi"] = agi_info
    except Exception as e:
        print("[WorldModel] next_hint_for_veritas_agi skipped:", e)

    return JSONResponse(content=payload, status_code=200)

# ---- Fuji quick validate ----
@app.post("/v1/fuji/validate", response_model=FujiDecision, dependencies=[Depends(require_api_key)])
def fuji_validate(payload: dict):
    return JSONResponse(content=fuji_core.validate(payload.get("action",""), payload.get("context",{})))

# ---- Memory ----
@app.post("/v1/memory/put")
def memory_put(body: dict):
    """
    後方互換:
      - 旧: {user_id, key, value}
    新方式:
      - {kind: "semantic"|"episodic"|"skills", text, tags?, meta?}
      - 両方同時に来たら両方保存（レガシー＆新MemoryOS）
    """
    try:
        # ---- 旧フォーマット（レガシーKV）対応 ----
        user_id = body.get("user_id", "anon")
        key = body.get("key") or f"memory_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        value = body.get("value") or {}

        legacy_saved = False
        if value:  # 旧仕様が来ている場合のみ
            try:
                mem.put(user_id, key, value)
                legacy_saved = True
            except Exception as e:
                print("[MemoryOS][legacy] Error:", e)

        # ---- 新フォーマット（ベクトル検索用）----
        # デフォルトは semantic に入れる（短文の知識/要約向け）
        kind = (body.get("kind") or "semantic").strip().lower()
        if kind not in ("semantic", "episodic", "skills"):
            kind = "semantic"

        text = (body.get("text") or "").strip()
        tags = body.get("tags") or []
        meta = body.get("meta") or {}

        new_id = None
        if text:
            try:
                text_clean = redact(text)
                new_id = MEM.put(kind, {"text": text_clean, "tags": tags, "meta": meta})
            except Exception as e:
                print("[MemoryOS][vector] Error:", e)

        # ---- 応答 ----
        return {
            "ok": True,
            "legacy": {"saved": legacy_saved, "key": key if legacy_saved else None},
            "vector": {
                "saved": bool(new_id),
                "id": new_id,
                "kind": kind if new_id else None,
                "tags": tags if new_id else None,
            },
            "size": len(str(value)) if value else len(text),
        }

    except Exception as e:
        print("[MemoryOS] Error:", e)
        return {"ok": False, "error": str(e)}

@app.post("/v1/memory/search")
async def memory_search(payload: dict):
    q = payload.get("query","")
    kinds = payload.get("kinds")
    k = int(payload.get("k", 8))
    min_sim = float(payload.get("min_sim", 0.25))
    return {"ok": True, "hits": MEM.search(q, k=k, kinds=kinds, min_sim=min_sim)}

@app.post("/v1/memory/get", dependencies=[Depends(require_api_key)])
def memory_get(body: dict): return {"value": mem.get(body["user_id"], body["key"])}

# ---- metrics for Doctor ----
@app.get("/v1/metrics")
def metrics():
    from glob import glob
    files = sorted(glob(str(SHADOW_DIR / "decide_*.json")))
    last_at = None
    if files:
        try:
            with open(files[-1], encoding="utf-8") as f:
                last_at = json.load(f).get("created_at")
        except Exception:
            pass
    lines = 0
    if LOG_JSONL.exists():
        with open(LOG_JSONL, encoding="utf-8") as f:
            for _ in f: lines += 1
    return {"decide_files": len(files), "trust_jsonl_lines": lines, "last_decide_at": last_at,
            "server_time": datetime.utcnow().isoformat() + "Z"}
# ---- Trust Feedback ----
@app.post("/v1/trust/feedback")
def trust_feedback(body: dict):
    """
    人間からのフィードバックを trust_log.jsonl に記録する簡易API。
    Swagger から:
      {
        "user_id": "test_user",
        "score": 0.9,
        "note": "今日のプランはかなり良い",
        "source": "swagger"
      }
    みたいに送ればOK。
    """
    try:
        uid = (body.get("user_id") or "anon")
        score = body.get("score", 0.5)
        note = body.get("note") or ""
        source = body.get("source") or "manual"

        # 何か追加情報を残したければ extra に入れる
        extra = {
            "api": "/v1/trust/feedback",
        }

        value_core.append_trust_log(
            user_id=uid,
            score=score,
            note=note,
            source=source,
            extra=extra,
        )
        return {"status": "ok", "user_id": uid}
    except Exception as e:
        print("[Trust] feedback failed:", e)
        return {"status": "error", "detail": str(e)}

