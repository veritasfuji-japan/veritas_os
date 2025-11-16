#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS decide (CLI)
- personas/styles/tones を前置きして /v1/decide を叩く
- --apply-safe 指定時、FUJI が `modify` なら安全化して 2 回目を自動送信
"""

import os, sys, json, argparse, hmac, hashlib, time, uuid, requests, re
from pathlib import Path
from datetime import datetime

# ===== 固定パス =====
REPO_ROOT = Path("/Users/user/veritas_clean_test2/veritas_os")
LOG_DIR   = REPO_ROOT / "scripts" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# テンプレート: veritas_os/templates/*
TEMPLATE_ROOT = REPO_ROOT / "templates"

# API 接続情報（環境変数が優先）
API_BASE   = os.environ.get("VERITAS_API_BASE", "http://127.0.0.1:8000")
API_KEY    = os.environ.get("VERITAS_API_KEY", "")
API_SECRET = os.environ.get("VERITAS_API_SECRET", "")


# デフォルト persona/style/tone
DEFAULTS = {
    "persona": "default",
    "style": "concise",
    "tone": "friendly",
}

# ---------- helpers ----------
def _load_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def _load_template(kind: str, name: str) -> str:
    return _load_text(TEMPLATE_ROOT / kind / f"{name}.txt")

def _sign(ts: int, nonce: str, body: str) -> str:
    msg = f"{ts}\n{nonce}\n{body}"
    return hmac.new(API_SECRET.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()

def _headers_for(body: str) -> dict:
    ts    = int(time.time())
    nonce = uuid.uuid4().hex
    sig   = _sign(ts, nonce, body)
    return {
        "X-API-Key": API_KEY,
        "X-Timestamp": str(ts),
        "X-Nonce": nonce,
        "X-Signature": sig,
        "Content-Type": "application/json",
    }

def _post_decide(payload: dict) -> requests.Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    url  = f"{API_BASE}/v1/decide"
    return requests.post(url, headers=_headers_for(body), data=body)

# --- ざっくりPII検出（fuji.py と整合） ---
_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'(東京都|都|道|府|県|市|区|町|村).{0,20}\d')
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}')

def _mask_with_redactions(text: str, redactions: list[str]) -> str:
    """FUJI の redactions に合わせてざっくりマスク（過剰マスク可）"""
    if not text or not redactions:
        return text
    out = text
    changed = False
    if "電話" in redactions:
        new = _RE_PHONE.sub("〇〇-〇〇〇〇-〇〇〇〇", out); changed |= (new != out); out = new
    if "メール" in redactions:
        new = _RE_EMAIL.sub("xx@masked.xx", out);         changed |= (new != out); out = new
    if "住所" in redactions:
        new = _RE_ADDRJP.sub("〇〇県〇〇市〇〇", out);     changed |= (new != out); out = new
    if "個人名" in redactions:
        new = _RE_NAMEJP.sub(lambda m: m.group(0)[0] + "●●", out); changed |= (new != out); out = new
    for term in redactions:
        if term and term in out:
            out = out.replace(term, "〇〇")
    if not changed:
        out = re.sub(r'\d{2,}', lambda m: '〇' * len(m.group(0)), out)
    return out

def _save_txt(name: str, content: str):
    (LOG_DIR / name).write_text(content, encoding="utf-8")

def _save_json(name: str, obj: dict):
    (LOG_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- main ----------
def main():
    if not API_KEY or not API_SECRET:
        print("❌ 環境変数 VERITAS_API_KEY / VERITAS_API_SECRET を設定してください。")
        sys.exit(1)

    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="ユーザ質問")
    ap.add_argument("--persona", default=DEFAULTS["persona"])
    ap.add_argument("--style",   default=DEFAULTS["style"])
    ap.add_argument("--tone",    default=DEFAULTS["tone"])
    ap.add_argument("--min-evidence", type=int, default=2, help="必要エビデンス数(1-3推奨)")
    ap.add_argument("--options", nargs="*", default=[], help="選択肢（スペース/カンマ/スラッシュでもOK）")
    ap.add_argument("--apply-safe", action="store_true", help="FUJIがmodifyの時だけ安全化→再送する")
    ap.add_argument("--user-id", default="cli")
    args = ap.parse_args()

    # ---- templates → 前置き ----
    persona = _load_template("personas", args.persona)
    style   = _load_template("styles",   args.style)
    tone    = _load_template("tones",    args.tone)

    preamble = "\n".join([t for t in [persona, style and f"Style: {style}", tone and f"Tone: {tone}"] if t])
    context_query = f"{preamble}\n\nUser: {args.query}"

    # ---- options を正規化 ----
    opts = args.options
    if isinstance(opts, list):
        if len(opts) == 1 and isinstance(opts[0], str):
            opts = [s for s in re.split(r"[,/、\s]+", opts[0]) if s]
    elif isinstance(opts, str):
        opts = [s for s in re.split(r"[,/、\s]+", opts) if s]
    else:
        opts = []

    # ---- 1st request ----
    payload1 = {
        "context": {
            "user_id": args.user_id,
            "query": context_query,
            "time_horizon": "mid",
            "telos_weights": {"W_Transcendence": 0.6, "W_Struggle": 0.4},
            "affect_hint": {"style": args.style},
        },
        "query": args.query,
        "options": opts,
        "min_evidence": int(args.min_evidence),
    }

    try:
        r1 = _post_decide(payload1)
    except Exception as e:
        print("❌ VERITAS: decide.py 送信エラー:", e)
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _save_txt(f"decide_status_{ts}.txt", f"{r1.status_code}")
    try:
        res1 = r1.json()
    except Exception:
        _save_txt(f"decide_error_{ts}.txt", r1.text)
        print(r1.text)
        return
    _save_json(f"decide_first_{ts}.json", {"request": payload1, "response": res1})

    gate = (res1.get("gate") or {})
    fuji = (res1.get("fuji") or {})
    status = (
        gate.get("decision_status")
        or fuji.get("status")
        or res1.get("decision_status")
    )
    print("[DBG] gate.decision_status=", gate.get("decision_status"))
    print("[DBG] fuji.status=", fuji.get("status"))
    print("[DBG] root.decision_status=", res1.get("decision_status"))
    print("[DBG] final status used=", status)

    # ---- allow/rejected or apply-safe disabled → そのまま表示 ----
    if not args.apply_safe:
        _save_txt(f"decide_second_skipped_{ts}.txt", "skip: apply_safe=false")
        print(json.dumps(res1, ensure_ascii=False, indent=2))
        return
    if status != "modify":
        _save_txt(
            f"decide_second_skipped_{ts}.txt",
            f"skip: status={status}, gate={gate.get('decision_status')}, fuji={fuji.get('status')}"
        )
        print(json.dumps(res1, ensure_ascii=False, indent=2))
        return

    # ---- FUJI modify → 自動安全化して 2nd request ----
    redactions = fuji.get("redactions") or []
    safe_notes = fuji.get("safe_instructions") or []
    mods = fuji.get("modifications") or []

    # ① 質問テキストをマスク
    safe_query = _mask_with_redactions(args.query, redactions)
    _save_txt(f"masked_query_{ts}.txt", safe_query)

    # ② 前置き付きの context.query もマスク版に置換（※ここが重要）
    context_query2 = f"{preamble}\n\nUser: {safe_query}"

    payload2 = {
        "context": {
            "user_id": args.user_id,
            "query": context_query2,          # マスク済み前置き
            "time_horizon": "mid",
            "telos_weights": {"W_Transcendence": 0.6, "W_Struggle": 0.4},
            "affect_hint": {"style": args.style},
            "fuji_safe_applied": True,
            "fuji_mods": mods,
            "fuji_notes": safe_notes,
        },
        "query": safe_query,                  # マスク済み本文
        "options": opts,
        "min_evidence": int(args.min_evidence),
    }

    # --- 送信前スナップショット（必ず作成） ---
    _save_json(f"decide_second_attempt_{ts}.json", {"request": payload2, "note": "before_post"})

    try:
        r2 = _post_decide(payload2)
        _save_txt(f"decide_second_http_{ts}.txt", f"status={r2.status_code}\n{r2.text[:8000]}")
        res2 = r2.json()
    except Exception as e:
        _save_txt(
            f"decide_second_error_{ts}.txt",
            f"EXC={repr(e)}\nstatus={getattr(r2,'status_code',None)}\n{getattr(r2,'text','')[:8000]}"
        )
        print("❌ VERITAS: 2回目送信エラー:", e)
        print(json.dumps(res1, ensure_ascii=False, indent=2))
        return

    final = dict(res2)
    final.setdefault("extras", {})
    final["extras"].setdefault("fuji_applied", True)
    final["extras"].setdefault("fuji_first_gate", gate)
    final["extras"].setdefault("safe_instructions", safe_notes)
    final["extras"].setdefault("redactions", redactions)

    print(f"[DBG] second.gate.decision_status= {(final.get('gate') or {}).get('decision_status')}")
    print(f"[DBG] second.root.decision_status= {final.get('decision_status')}")

    _save_json(f"decide_second_{ts}.json", {
        "request": payload2,
        "response": final,
        "fuji_from_first": fuji
    })

    print(json.dumps(final, ensure_ascii=False, indent=2))
    print("✅ decide done")
    print("✅ full run completed")

if __name__ == "__main__":
    main()
