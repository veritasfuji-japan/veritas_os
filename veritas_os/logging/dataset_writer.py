# veritas/logging/dataset_writer.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import json, hashlib, time, os
from veritas_os.core.config import cfg
from .paths import LOG_DIR, DATASET_DIR, DASH_DIR

# === パス設定（最新版） =====================================
# このファイル:
#   .../veritas_clean_test2/veritas_os/veritas/logging/dataset_writer.py
# を想定
# parents[0] = .../veritas/logging
# parents[1] = .../veritas
# parents[2] = .../veritas_os  ← ここがリポジトリルート
# ==== PATH 統一 ====
DATASET_DIR = cfg.dataset_dir               # .../veritas_os/scripts/datasets
DATASET_DIR.mkdir(parents=True, exist_ok=True)

DATASET_JSONL = DATASET_DIR / "dataset.jsonl"   # ← ここが今回の missing point！

# ==========================================================


# -------------------------
# helpers
# -------------------------
def _sha256_dict(d: Dict[str, Any]) -> str:
    try:
        s = json.dumps(d, ensure_ascii=False, sort_keys=True)
    except Exception:
        s = str(d)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _f2(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _summarize_alternatives(alts: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in (alts or [])[:k]:
        out.append({
            "id": a.get("id"),
            "title": a.get("title") or a.get("text"),
            "score": _f2(a.get("score"), 1.0),
        })
    return out


def _summarize_evidence(evs: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in (evs or [])[:k]:
        out.append({
            "source": e.get("source"),
            "confidence": _f2(e.get("confidence"), 0.0),
            "snippet": e.get("snippet"),
        })
    return out


# ==========================
#    Record Builder
# ==========================
def build_dataset_record(
    req_payload: Dict[str, Any],
    res_payload: Dict[str, Any],
    meta: Dict[str, Any],
    eval_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    🔥 AGI化 Stage2: 自己学習データセット構造
    - world.utility など世界モデル要素
    - memory_os usage log（活用/引用）
    - FUJI Gate 情報
    - alternatives / evidence summary
    """

    chosen = (res_payload or {}).get("chosen") or {}
    alts   = (res_payload or {}).get("alternatives") or []
    evs    = (res_payload or {}).get("evidence") or []
    fuji   = (res_payload or {}).get("fuji") or {}
    gate   = (res_payload or {}).get("gate") or {}

    world  = chosen.get("world", {}) if chosen else {}

    # MemoryOS usage
    mem = (res_payload or {}).get("memory", {})
    mem_used     = mem.get("used", False)
    mem_citation = mem.get("citations", 0)

    decision_labels = {
        "status": gate.get("decision_status", "allow"),
        "fuji_status": fuji.get("status"),
        "blocked": (gate.get("decision_status") == "rejected"),
        "memory_used": mem_used,
        "memory_citations": mem_citation,
    }

    # -------------------------
    # Main Record
    # -------------------------
    rec = {
        "ts": int(time.time() * 1000),

        # ----- Input -----
        "request": {
            "payload": req_payload,
            "hash": _sha256_dict(req_payload),
        },

        # ----- Output -----
        "response": {
            "payload": res_payload,
            "hash": _sha256_dict(res_payload),

            # chosen
            "chosen": {
                "id": chosen.get("id"),
                "title": chosen.get("title"),
                "score": _f2(chosen.get("score"), 1.0),
                "utility": _f2(world.get("utility"), 0.0),
                "risk": _f2(world.get("predicted_risk"), 0.0),
                "benefit": _f2(world.get("predicted_benefit"), 0.0),
                "cost": _f2(world.get("predicted_cost"), 0.0),
            },

            # summaries
            "alternatives": _summarize_alternatives(alts),
            "evidence": _summarize_evidence(evs),

            # safety
            "fuji": {
                "status": fuji.get("status"),
                "reasons": fuji.get("reasons", []),
                "violations": fuji.get("violations", []),
            },

            "gate": {
                "decision_status": gate.get("decision_status"),
                "risk": _f2(gate.get("risk"), 0.0),
                "telos_score": _f2(gate.get("telos_score"), 0.0),
                "reason": gate.get("reason"),
            },

            # MemoryOS
            "memory": {
                "used": mem_used,
                "citations": mem_citation,
            },
        },

        # ----- meta -----
        "meta": meta or {},
        "eval": eval_meta or {},

        # ----- labels（学習ターゲット） -----
        "labels": decision_labels,

        # version
        "version": {
            "api": meta.get("api_version") if meta else None,
            "kernel": meta.get("kernel_version") if meta else None,
        },
    }

    return rec


# ==========================
#    Append (JSONL)
# ==========================
# ==== 書き込み関数 ====
def append_dataset_record(record: Dict[str, Any], path: Path = DATASET_JSONL):
    """
    dataset.jsonl に LLM 学習用の決定記録を追記する（決定ログ）
    """
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] append_dataset_record failed: {e}")
