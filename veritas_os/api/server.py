# veritas/api/server.py
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4  # 今後の拡張用に残しておく

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY  # noqa: F401

# ---- VERITAS core 層 ----
from veritas_os.core import fuji as fuji_core, memory as mem, value_core
from veritas_os.core.config import cfg
from veritas_os.core import pipeline as decision_pipeline

# ---- ログ／メモリ層 ----
from veritas_os.logging.dataset_writer import (
    build_dataset_record,
    append_dataset_record,
)
from veritas_os.logging.paths import LOG_DIR, DATASET_DIR, VAL_JSON, META_LOG
from veritas_os.core.memory import MEM as MEMORY_STORE
# ---- API 層 ----
from veritas_os.api.schemas import (
    DecideRequest,
    DecideResponse,
    FujiDecision,
    ChatRequest,
    ValuesOut,
)
from veritas_os.api.constants import DECISION_ALLOW, DECISION_REJECTED
from veritas_os.api.evolver import load_persona

# ==============================
# 環境 & パス初期化
# ==============================

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os
load_dotenv(REPO_ROOT / ".env")

app = FastAPI(title="VERITAS Public API", version="1.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

START_TS = time.time()

# trust_log / shadow_decide のパス
LOG_JSON = LOG_DIR / "trust_log.json"
LOG_JSONL = LOG_DIR / "trust_log.jsonl"
SHADOW_DIR = LOG_DIR / "DASH"
SHADOW_DIR.mkdir(parents=True, exist_ok=True)

# ==============================
# API Key & HMAC 認証
# ==============================

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
_nonce_store: Dict[str, float] = {}


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
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_timestamp: Optional[str] = Header(default=None, alias="X-Timestamp"),
    x_nonce: Optional[str] = Header(default=None, alias="X-Nonce"),
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
):
    """
    CLI 署名テスト用の HMAC 検証。
    必須にしたい場合はエンドポイント側の dependencies に Depends(verify_signature) を追加。
    """
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

    body_bytes = await request.body()
    body = body_bytes.decode("utf-8") if body_bytes else ""
    payload = f"{ts}\n{x_nonce}\n{body}"

    mac = hmac.new(API_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    if not hmac.compare_digest(mac, (x_signature or "").lower()):
        raise HTTPException(status_code=401, detail="Invalid signature")
    return True


# ---- rate limit（簡易）----
_RATE_LIMIT = 60
_RATE_WINDOW = 60.0
_rate_bucket: Dict[str, tuple[int, float]] = {}


def enforce_rate_limit(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")
):
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


# ==============================
# 共通ユーティリティ
# ==============================

def redact(text: str) -> str:
    """
    メモリ保存時などに軽く PII マスクするための簡易 redactor。
    """
    if not text:
        return text
    # email
    text = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[redacted@email]", text)
    # phone (かなりラフ)
    text = re.sub(r"\b\d{2,4}[-・\s]?\d{2,4}[-・\s]?\d{3,4}\b", "[redacted:phone]", text)
    return text


# ==============================
# 422 エラーの見やすい返却
# ==============================

def _decide_example() -> dict:
    return {
        "context": {"user_id": "demo"},
        "query": "VERITASを進化させるには？",
        "options": [{"title": "最小ステップで前進"}],
        "min_evidence": 1,
    }


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    raw_body_bytes = await request.body()
    raw = raw_body_bytes.decode("utf-8", "replace") if raw_body_bytes else ""
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "hint": {"expected_example": _decide_example()},
            "raw_body": raw,
        },
    )


# ==============================
# Health / Status
# ==============================

@app.get("/health")
@app.get("/v1/health")
def health():
    return {"ok": True, "uptime": int(time.time() - START_TS)}


@app.get("/status")
@app.get("/v1/status")
@app.get("/api/status")
def status():
    return {
        "ok": True,
        "version": "veritas-api 1.0.1",
        "uptime": int(time.time() - START_TS),
    }


# ==============================
# Trust log helpers（server 側でも軽く読めるように）
# ==============================

def _load_logs_json() -> list:
    try:
        with open(LOG_JSON, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            return obj.get("items", [])
        if isinstance(obj, list):
            return obj
        return []
    except Exception:
        return []


def _save_json(items: list) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_JSON, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)


def append_trust_log(entry: dict) -> None:
    """
    pipeline 側でも同名関数を持っているが、
    server側から直接書きたいケース向けの軽量ヘルパー。
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    items = _load_logs_json()
    items.append(entry)
    _save_json(items)


def write_shadow_decide(
    request_id: str,
    body: dict,
    chosen: dict,
    telos_score: float,
    fuji: dict,
) -> None:
    """
    ざっくり Doctor 用の「1 decide の影ログ」を保存。
    pipeline 側実装と揃えてある。
    """
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = SHADOW_DIR / f"decide_{ts}.json"
    rec = {
        "request_id": request_id,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "query": (body.get("query") or (body.get("context") or {}).get("query") or ""),
        "chosen": chosen,
        "telos_score": float(telos_score or 0.0),
        "fuji": (fuji or {}).get("status"),
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)


# ==============================
# main: /v1/decide
# ==============================

@app.post(
    "/v1/decide",
    response_model=DecideResponse,
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
async def decide(req: DecideRequest, request: Request):
    """
    VERITAS のメイン Decision API。
    ロジック本体は veritas_os.core.pipeline.run_decide_pipeline 側に集約。
    """
    payload = await decision_pipeline.run_decide_pipeline(req=req, request=request)
    return JSONResponse(content=payload, status_code=200)


# ==============================
# FUJI quick validate
# ==============================

@app.post(
    "/v1/fuji/validate",
    response_model=FujiDecision,
    dependencies=[Depends(require_api_key)],
)
def fuji_validate(payload: dict):
    """
    FUJIゲートの単体テスト用エンドポイント。
    現在の fuji_core は validate_action(action, context) を提供している前提に合わせる。
    古い実装で validate(...) があればそちらにもフォールバック。
    """
    action = payload.get("action", "") or ""
    context = payload.get("context") or {}

    # 新API: validate_action を優先
    if hasattr(fuji_core, "validate_action"):
        result = fuji_core.validate_action(action, context)

    # 互換用: もし古い fuji_core に validate があれば使う
    elif hasattr(fuji_core, "validate"):
        result = fuji_core.validate(action, context)  # type: ignore

    else:
        raise HTTPException(
            status_code=500,
            detail="fuji_core has neither validate_action nor validate",
        )

    # result は dict 想定（FujiDecision でバリデーションされる）
    return JSONResponse(content=result)


# ==============================
# Memory API
# ==============================

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
                # mem でも MEM でもOKだが、統一のため MEMORY_STORE を使用
                MEMORY_STORE.put(user_id, key, value)
                legacy_saved = True
            except Exception as e:
                print("[MemoryOS][legacy] Error:", e)

        # ---- 新フォーマット（MemoryOS episodic 用）----
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

                # MemoryStore に「エピソード」として保存
                # meta に user_id / kind も入れておく
                meta_for_store = dict(meta)
                meta_for_store.setdefault("user_id", user_id)
                meta_for_store.setdefault("kind", kind)

                # ★ MEMORY_STORE は veritas_os.core.memory のグローバル MemoryStore
                if hasattr(MEMORY_STORE, "put_episode"):
                    # put_episode は episode_xxx という key を返す（memory.py 側修正版）
                    new_id = MEMORY_STORE.put_episode(
                        text=text_clean,
                        tags=tags,
                        meta=meta_for_store,
                    )
                else:
                    # 互換フォールバック（古い memory.py 用）
                    episode_key = f"episode_{int(time.time())}"
                    MEMORY_STORE.put(
                        user_id,
                        episode_key,
                        {
                            "text": text_clean,
                            "tags": tags,
                            "meta": meta_for_store,
                        },
                    )
                    new_id = episode_key

            except Exception as e:
                print("[MemoryOS][vector] Error:", e)

        # ---- 応答 ----
        return {
            "ok": True,
            "legacy": {
                "saved": legacy_saved,
                "key": key if legacy_saved else None,
            },
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
    """
    ベクトル検索エンドポイント
    
    Request:
        {
            "query": "検索クエリ",
            "kinds": ["semantic", "episodic"] (optional),
            "k": 8 (optional, default: 8),
            "min_sim": 0.25 (optional, default: 0.25),
            "user_id": "user123" (optional)
        }
    
    Response:
        {
            "ok": true,
            "hits": [
                {
                    "text": "...",
                    "score": 0.85,
                    "tags": [...],
                    "meta": {...}
                },
                ...
            ]
        }
    """
    try:
        q = payload.get("query", "")
        kinds = payload.get("kinds")  # None or ["semantic", "episodic"]
        k = int(payload.get("k", 8))
        min_sim = float(payload.get("min_sim", 0.25))
        user_id = payload.get("user_id")  # Noneの場合は全ユーザー検索

        hits = MEMORY_STORE.search(
            query=q,
            k=k,
            kinds=kinds,
            min_sim=min_sim,
        )
        
        # user_id フィルタリング（オプション）
        if user_id:
            hits = [
                h for h in hits
                if h.get("meta", {}).get("user_id") == user_id
            ]
        
        return {"ok": True, "hits": hits, "count": len(hits)}
    
    except Exception as e:
        print("[MemoryOS][search] Error:", e)
        return {"ok": False, "error": str(e), "hits": []}


@app.post("/v1/memory/get", dependencies=[Depends(require_api_key)])
def memory_get(body: dict):
    """レガシーKV取得"""
    try:
        value = MEMORY_STORE.get(body["user_id"], body["key"])
        return {"ok": True, "value": value}
    except Exception as e:
        return {"ok": False, "error": str(e), "value": None}


# ==============================
# metrics for Doctor
# ==============================

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
            for _ in f:
                lines += 1

    return {
        "decide_files": len(files),
        "trust_jsonl_lines": lines,
        "last_decide_at": last_at,
        "server_time": datetime.utcnow().isoformat() + "Z",
    }


# ==============================
# Trust Feedback
# ==============================

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

        extra = {"api": "/v1/trust/feedback"}

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


