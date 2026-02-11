# veritas_os/core/debate.py
"""
ReasonOS Multi-Agent Debate モジュール（実用性改善 + 安全弁/保険 強化版）

改善点（追加分）:
A) JSON救出の強化（途中で切れたJSONから options を回収）
B) verdict / score の正規化（未知値でも安定）
C) ハードブロック（blocked/fuji_block/safety_block が立っていたら絶対選ばない）
D) “危険っぽい”ヒューリスティクス保険（最後の砦）
E) 選択不能時は必ず safe_fallback（事故防止）

テスト互換:
- debate._safe_parse が存在し、各種パターンを dict として返す
- _fallback_debate は必ず先頭候補を chosen にする（o1 が選ばれる）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import logging
import re
import textwrap

from . import llm_client
from . import world as world_model
from .utils import _clamp01

logger = logging.getLogger(__name__)

DebateResult = Dict[str, Any]

_DANGER_TERMS_JA = [
    "自殺",
    "自傷",
    "死にたい",
    "爆弾",
    "銃",
    "麻薬",
    "ハッキング",
    "ウイルス",
    "侵入",
    "殺す",
    "暴力",
    "テロ",
    "違法",
]

_DANGER_PATTERNS_EN = [
    re.compile(r"\bkill myself\b", re.IGNORECASE),
    re.compile(r"\bweapon\b", re.IGNORECASE),
    re.compile(r"\bguns?\b", re.IGNORECASE),
    re.compile(r"\bdrugs?\b", re.IGNORECASE),
    re.compile(r"\bmalware\b", re.IGNORECASE),
    re.compile(r"\bvirus\b", re.IGNORECASE),
    re.compile(r"\bcrack(?:ing)?\b", re.IGNORECASE),
    re.compile(r"\bhack(?:ing)?\b", re.IGNORECASE),
    re.compile(r"\bterror(?:ism|ist)?\b", re.IGNORECASE),
    re.compile(r"\billegal\b", re.IGNORECASE),
]


# ============================
#  設定と定数
# ============================


class DebateMode:
    NORMAL = "normal"
    DEGRADED = "degraded"
    SAFE_FALLBACK = "safe_fallback"


SCORE_THRESHOLDS = {
    "normal_min": 0.4,
    "degraded_min": 0.2,
    "warning_threshold": 0.6,
}


# ============================
#  Prompt
# ============================


def _build_system_prompt() -> str:
    return textwrap.dedent("""
    あなたは「VERITAS OS」の ReasonOS / Debate モジュールです。
    以下の 4 つの役割を内部でシミュレーションしてください：
    1. Architect（構造設計）
    2. Critic（批判）
    3. Safety（安全・法的・倫理）
    4. Judge（総合審査）

    verdict は次の3つのみ：
      - "採用推奨"（目安 score>=0.6）
      - "要検討"（目安 0.3<=score<0.6）
      - "却下"（score<0.3 または重大問題）

    JSON のみで出力：
    {
      "options": [
        {
          "id": "step1",
          "score": 0.82,
          "score_raw": 0.82,
          "verdict": "採用推奨",
          "rejection_reason": null,
          "architect_view": "...",
          "critic_view": "...",
          "safety_view": "...",
          "summary": "..."
        }
      ],
      "chosen_id": "step1"
    }

    JSON 以外の文章は禁止。
    """)


def _build_user_prompt(
    query: str,
    options: List[Dict[str, Any]],
    context: Dict[str, Any],
    world_snapshot: Optional[Dict[str, Any]] = None,
) -> str:
    q = (query or "").strip()

    ctx_snip = json.dumps(
        {
            "user_id": context.get("user_id") or "anon",
            "stakes": context.get("stakes"),
            "telos_weights": context.get("telos_weights"),
        },
        ensure_ascii=False,
        indent=2,
    )

    opts_snip = json.dumps(options, ensure_ascii=False, indent=2)
    world_snip = json.dumps(world_snapshot or {}, ensure_ascii=False, indent=2)

    return textwrap.dedent(f"""
    # ユーザーの現在の問い / 目的
    {q}

    ---
    # 文脈情報（VERITAS コンテキスト抜粋）
    {ctx_snip}

    ---
    # WorldModel のスナップショット
    {world_snip}

    ---
    # 評価対象の候補一覧
    {opts_snip}

    ---
    少しでも前進できる候補があれば「要検討」を残し、
    最小ステップで前進しつつリスクが低いものを選び、
    指定JSON形式のみで出力してください。
    """)


# ============================
#  Safety Valve（保険）
# ============================


def _is_hard_blocked(opt: Dict[str, Any]) -> bool:
    """
    “絶対に選ばない”ハードブロック。
    FUJIが前段にいても、最後の砦として入れておく。
    """
    for key in ("blocked", "fuji_block", "safety_block", "is_blocked"):
        v = opt.get(key)
        if v is True or (isinstance(v, str) and v.strip().lower() in ("true", "1", "yes")):
            return True
    return False


def _normalize_text_for_scan(text: str) -> str:
    """Normalize text for safety keyword scanning."""
    return " ".join((text or "").lower().split())


def _looks_dangerous_text(opt: Dict[str, Any]) -> bool:
    """
    “念のため”の軽いヒューリスティクス保険。
    ※ ここは厳密判定ではなく、最後の事故防止。
    """
    text = " ".join(
        [
            str(opt.get("title") or ""),
            str(opt.get("detail") or ""),
            str(opt.get("description") or ""),
            str(opt.get("summary") or ""),
            str(opt.get("safety_view") or ""),
        ]
    )
    normalized = _normalize_text_for_scan(text)

    if any(term in normalized for term in _DANGER_TERMS_JA):
        return True

    return any(pattern.search(normalized) for pattern in _DANGER_PATTERNS_EN)


# ============================
#  Utility
# ============================


def _is_rejected(opt: Dict[str, Any]) -> bool:
    v = str(opt.get("verdict") or "").strip()
    return v in ("却下", "reject", "Rejected", "NG")


# _clamp01 は utils.py からインポート


def _get_score(opt: Dict[str, Any]) -> float:
    try:
        s = opt.get("score")
        if s is None:
            s = opt.get("score_raw")
        return _clamp01(float(s or 0.0))
    except Exception:
        return 0.0


def _normalize_verdict_by_score(opt: Dict[str, Any]) -> str:
    """
    verdict が壊れてる/未知の場合にスコアから補正して安定化。
    """
    v = str(opt.get("verdict") or "").strip()
    if v in ("採用推奨", "要検討", "却下"):
        return v

    score = _get_score(opt)
    if score >= 0.6:
        return "採用推奨"
    if score >= 0.3:
        return "要検討"
    return "却下"


def _calc_risk_delta(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
) -> float:
    if not chosen:
        return 0.30

    delta = 0.0
    safety_view = str(chosen.get("safety_view") or "").lower()
    critic_view = str(chosen.get("critic_view") or "").lower()
    verdict = _normalize_verdict_by_score(chosen)
    score = _get_score(chosen)

    risk_keywords = {
        "危険": 0.15,
        "重大": 0.12,
        "リスク": 0.08,
        "問題": 0.05,
        "違反": 0.20,
        "禁止": 0.18,
        "illegal": 0.20,
        "ban": 0.15,
    }
    for kw, w in risk_keywords.items():
        if kw in safety_view:
            delta += w

    if verdict == "要検討":
        delta += 0.05
    elif verdict == "却下":
        delta += 0.25
    elif verdict == "採用推奨":
        if "問題なし" in safety_view or "安全" in safety_view:
            delta -= 0.05

    if score < 0.5:
        delta += (0.5 - score) * 0.2
    elif score > 0.8:
        if "問題" not in safety_view and "危険" not in safety_view:
            delta -= (score - 0.8) * 0.05

    if any(w in critic_view for w in ["致命", "深刻", "重大", "critical"]):
        delta += 0.10

    delta = max(-0.30, min(0.50, delta))
    return round(delta, 3)


def _build_debate_summary(
    chosen: Optional[Dict[str, Any]],
    options: List[Dict[str, Any]],
    mode: str,
) -> Dict[str, Any]:
    total = len(options)
    rejected_count = len([o for o in options if _is_rejected(o)])
    scores = [_get_score(o) for o in options]
    avg_score = sum(scores) / len(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    min_score = min(scores) if scores else 0.0

    return {
        "total_options": total,
        "rejected_count": rejected_count,
        "accepted_count": total - rejected_count,
        "mode": mode,
        "chosen_score": _get_score(chosen) if chosen else 0.0,
        "chosen_verdict": (chosen or {}).get("verdict"),
        "avg_score": round(avg_score, 3),
        "max_score": round(max_score, 3),
        "min_score": round(min_score, 3),
        "source": "debate.v3_safety_valve",
    }


def _create_warning_message(chosen: Dict[str, Any], mode: str, all_rejected: bool) -> str:
    score = _get_score(chosen)
    verdict = _normalize_verdict_by_score(chosen)

    warnings: List[str] = []

    if mode == DebateMode.DEGRADED:
        warnings.append("⚠️ 全候補が通常基準を満たしませんでした")
        warnings.append(f"最もスコアの高い候補（{score:.2f}）を選択しましたが、慎重な検討が必要です")

    if score < SCORE_THRESHOLDS["warning_threshold"]:
        warnings.append(f"⚠️ 選択候補のスコアが低めです（{score:.2f}）")

    if verdict == "却下":
        warnings.append("⚠️ この候補は本来却下寄りです。実行するなら代替案/安全策が必要です")
    elif verdict == "要検討":
        warnings.append("ℹ️ この候補にはリスクがあります。実行前に詳細を確認してください")

    safety_view = str(chosen.get("safety_view") or "")
    if any(kw in safety_view for kw in ["危険", "リスク", "問題", "違反"]):
        warnings.append(f"⚠️ 安全性の懸念: {safety_view}")

    return "\n".join(warnings) if warnings else ""


# ============================
#  JSON Parse（保険強化）
# ============================


def _safe_json_extract_like(raw: str) -> Dict[str, Any]:
    """
    planner._safe_json_extract と同格の“救出力”を持つ版。
    - ```json ブロック除去
    - dict/list ラップ
    - {} 抜き出し
    - 末尾削り
    - "options" 配列から完成オブジェクト救出（最後の保険）
    """
    if not raw:
        return {"options": [], "chosen_id": None}

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_nl = cleaned.find("\n")
        if first_nl != -1:
            cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

    # Security constraints
    MAX_STRING_LENGTH = 10000  # Maximum length for any string field
    MAX_OPTIONS = 100  # Maximum number of options to prevent resource exhaustion

    def _truncate_string(value: Any, max_len: int = MAX_STRING_LENGTH) -> Optional[str]:
        """Safely truncate string values to prevent resource exhaustion.

        If *max_len* is non-positive, falls back to ``MAX_STRING_LENGTH``.
        """
        if value is None:
            return None
        if max_len <= 0:
            max_len = MAX_STRING_LENGTH
        if not isinstance(value, str):
            return str(value)[:max_len]
        return value[:max_len]

    def _validate_option(opt: Any) -> bool:
        """Validate that an option has expected structure."""
        if not isinstance(opt, dict):
            return False
        # Options must have valid types for key fields if present
        for key in ("id", "title", "summary", "verdict"):
            val = opt.get(key)
            if val is not None and not isinstance(val, str):
                return False
            # Check string length limits
            if isinstance(val, str) and len(val) > MAX_STRING_LENGTH:
                return False
        for key in ("score", "score_raw"):
            if key in opt:
                try:
                    float(opt[key])
                except (TypeError, ValueError):
                    return False
        return True

    def _sanitize_options(options: List[Any]) -> List[Dict[str, Any]]:
        """Filter and sanitize options list to prevent malicious data."""
        sanitized = []
        for opt in options[:MAX_OPTIONS]:  # Limit number of options
            if _validate_option(opt):
                # Truncate string fields for safety
                for key in ("id", "title", "summary", "verdict", "safety_view", "critic_view", "architect_view"):
                    if key in opt and opt[key] is not None:
                        opt[key] = _truncate_string(opt[key])
                sanitized.append(opt)
            else:
                logger.warning("DebateOS: Skipping invalid option structure: %r", type(opt))
        if len(options) > MAX_OPTIONS:
            logger.warning("DebateOS: Truncated options from %d to %d", len(options), MAX_OPTIONS)
        return sanitized

    def _wrap(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, dict):
            options = obj.get("options") or []
            if not isinstance(options, list):
                options = []
            obj["options"] = _sanitize_options(options)
            chosen_id = obj.get("chosen_id")
            obj["chosen_id"] = _truncate_string(chosen_id, 1000) if isinstance(chosen_id, (str, type(None))) else None
            return obj
        if isinstance(obj, list):
            return {"options": _sanitize_options(obj), "chosen_id": None}
        return {"options": [], "chosen_id": None}

    try:
        return _wrap(json.loads(cleaned))
    except Exception:
        pass

    try:
        start = cleaned.index("{")
        end = cleaned.rindex("}") + 1
        return _wrap(json.loads(cleaned[start:end]))
    except Exception:
        pass

    # 末尾削り（軽め）
    attempts = 0
    for cut in range(len(cleaned), 1, -1):
        if attempts >= 250:
            break
        if cleaned[cut - 1] not in ("}", "]"):
            continue
        attempts += 1
        try:
            return _wrap(json.loads(cleaned[:cut]))
        except Exception:
            continue

    # "options":[{...},{...}] から完成objだけ拾う（最後の保険）
    def _extract_objects_from_array(text: str, key: str, max_objects: int = 50) -> List[Dict[str, Any]]:
        idx = text.find(f'"{key}"')
        if idx == -1:
            return []
        idx = text.find("[", idx)
        if idx == -1:
            return []

        i = idx + 1
        n = len(text)
        in_str = False
        esc = False
        depth = 0
        buf_start: Optional[int] = None
        objs: List[Dict[str, Any]] = []

        while i < n:
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    if depth == 0:
                        buf_start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and buf_start is not None:
                        s = text[buf_start : i + 1]
                        try:
                            objs.append(json.loads(s))
                        except Exception:
                            pass
                        buf_start = None
                        if len(objs) >= max_objects:
                            break
                elif ch == "]":
                    break
            i += 1
        return objs

    rescued = _extract_objects_from_array(cleaned, "options")
    if rescued:
        return {"options": _sanitize_options(rescued), "chosen_id": None}

    return {"options": [], "chosen_id": None}


# ---- テスト互換: debate._safe_parse を提供 ----
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

def _safe_parse(raw: Any) -> Dict[str, Any]:
    """
    テストが直接呼ぶユーティリティ。
    - dict -> dict (options/chosen_id を補完)
    - list -> {"options": list, "chosen_id": None}
    - str -> _safe_json_extract_like で救出
    - それ以外 -> str化して救出
    """
    if raw is None:
        return {"options": [], "chosen_id": None}

    if isinstance(raw, dict):
        d = dict(raw)
        d.setdefault("options", d.get("options") or [])
        d.setdefault("chosen_id", d.get("chosen_id"))
        return d

    if isinstance(raw, list):
        return {"options": raw, "chosen_id": None}

    if not isinstance(raw, str):
        raw = str(raw)

    s = raw.strip()
    if not s:
        return {"options": [], "chosen_id": None}

    # fenced json の場合は中身に寄せる（保険）
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    return _safe_json_extract_like(s)


# ============================
#  Selection
# ============================


def _select_best_candidate(
    enriched_list: List[Dict[str, Any]],
    min_score: float,
    allow_rejected: bool = False,
) -> Optional[Dict[str, Any]]:
    candidates = enriched_list

    # ハードブロック除外（安全弁）
    candidates = [o for o in candidates if not _is_hard_blocked(o)]

    if not allow_rejected:
        candidates = [o for o in candidates if not _is_rejected(o)]

    candidates = [o for o in candidates if _get_score(o) >= min_score]

    if not candidates:
        return None

    # tie-break: score → id（安定）
    return max(candidates, key=lambda o: (_get_score(o), str(o.get("id") or "")))


def _create_degraded_choice(enriched_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    degraded_min = SCORE_THRESHOLDS["degraded_min"]

    cand = _select_best_candidate(enriched_list, min_score=degraded_min, allow_rejected=True)
    if cand:
        logger.warning(
            "DebateOS: Degraded mode selected id=%s score=%.2f verdict=%s",
            cand.get("id"),
            _get_score(cand),
            _normalize_verdict_by_score(cand),
        )
        return cand

    # それでも無理なら “ハードブロック以外” の最高スコア（最後の最後）
    pool = [o for o in enriched_list if not _is_hard_blocked(o)]
    if pool:
        cand = max(pool, key=lambda o: (_get_score(o), str(o.get("id") or "")))
        logger.warning(
            "DebateOS: Emergency degraded pick id=%s score=%.2f",
            cand.get("id"),
            _get_score(cand),
        )
        return cand

    return None


# ============================
#  Fallback
# ============================


def _fallback_debate(options: List[Dict[str, Any]]) -> DebateResult:
    """
    テスト要件:
    - mode == DebateMode.SAFE_FALLBACK
    - source == DebateMode.SAFE_FALLBACK
    - chosen は必ず先頭候補（o1）になる（同点タイブレで o2 にしない）
    """
    if not options:
        return {
            "options": [],
            "chosen": None,
            "raw": None,
            "source": DebateMode.SAFE_FALLBACK,
            "mode": DebateMode.SAFE_FALLBACK,
            "risk_delta": 0.30,
            "warnings": ["⚠️ 候補が存在しないため選択できません"],
            "debate_summary": _build_debate_summary(None, [], DebateMode.SAFE_FALLBACK),
        }

    enriched: List[Dict[str, Any]] = []
    for idx, opt in enumerate(options, start=1):
        o = dict(opt) if isinstance(opt, dict) else {"title": str(opt)}
        o.setdefault("id", o.get("id") or o.get("title") or f"opt_{idx}")
        o.setdefault("title", o.get("title") or "候補")
        o["score"] = 0.5
        o["score_raw"] = 0.5
        o["verdict"] = "要検討"
        o["rejection_reason"] = None
        o["architect_view"] = "フォールバック: Architect 評価なし"
        o["critic_view"] = "フォールバック: Critic 評価なし"
        o["safety_view"] = "フォールバック: Safety 評価なし"
        o["summary"] = "LLM 失敗により暫定選択。"
        enriched.append(o)

    # ★ 重要: fallback は「入力順で最初」を chosen にする（テスト期待）
    chosen = enriched[0]

    # ただし、先頭がハードブロックなら「最初の非ブロック」を選ぶ（事故防止）
    if _is_hard_blocked(chosen):
        for cand in enriched:
            if not _is_hard_blocked(cand):
                chosen = cand
                break

    risk_delta = _calc_risk_delta(chosen, enriched)
    summary = _build_debate_summary(chosen, enriched, DebateMode.SAFE_FALLBACK)

    warning = _create_warning_message(chosen, DebateMode.SAFE_FALLBACK, False)
    warning = "⚠️ LLM評価失敗により安全フォールバックを使用\n" + (warning or "")

    return {
        "options": enriched,
        "chosen": chosen,
        "raw": None,
        "source": DebateMode.SAFE_FALLBACK,
        "mode": DebateMode.SAFE_FALLBACK,
        "risk_delta": risk_delta,
        "warnings": [w for w in warning.split("\n") if w.strip()],
        "debate_summary": summary,
    }


# ============================
#  Main
# ============================


def run_debate(
    query: str,
    options: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> DebateResult:
    ctx = dict(context or {})

    try:
        world_snap = world_model.snapshot("veritas_agi")
    except Exception:
        world_snap = {}

    if not options:
        logger.warning("DebateOS: No options provided")
        return _fallback_debate(options)

    # 入力候補の最低正規化（id/title無いとマージで事故る）
    base_options: List[Dict[str, Any]] = []
    for i, o in enumerate(options, start=1):
        if not isinstance(o, dict):
            continue
        x = dict(o)
        x.setdefault("id", x.get("id") or x.get("title") or f"opt_{i}")
        x.setdefault("title", x.get("title") or "候補")
        base_options.append(x)

    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(query, base_options, ctx, world_snap)

    try:
        res = llm_client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            extra_messages=None,
            temperature=0.25,
            max_tokens=1000,
        )
        raw_text = res.get("text") if isinstance(res, dict) else str(res)

        # ★ テスト互換的にも _safe_parse を経由してOK
        parsed = _safe_parse(raw_text)

        out_opts = parsed.get("options") or []
        chosen_id = parsed.get("chosen_id")

        # base を id で管理
        enriched_by_id: Dict[str, Dict[str, Any]] = {}
        for base in base_options:
            bid = base.get("id") or base.get("title") or "opt"
            enriched_by_id[str(bid)] = dict(base)

        # LLM結果をマージ（id一致が基本。idが壊れてたら title一致も試す）
        by_title = {str(v.get("title") or ""): k for k, v in enriched_by_id.items()}

        for o in out_opts:
            if not isinstance(o, dict):
                continue
            oid = o.get("id")
            key = str(oid) if oid and str(oid) in enriched_by_id else None
            if key is None:
                t = str(o.get("title") or "")
                key = by_title.get(t)
            if not key:
                continue
            target = enriched_by_id[key]
            for k, v in o.items():
                target[k] = v

        enriched_list = list(enriched_by_id.values())

        # verdict/score 正規化（保険）
        for o in enriched_list:
            o["score"] = _get_score(o)
            o["score_raw"] = _get_score(o)
            o["verdict"] = _normalize_verdict_by_score(o)

        # ============================
        # 3段階選択 + 安全弁
        # ============================
        chosen: Optional[Dict[str, Any]] = None
        mode = DebateMode.NORMAL
        all_rejected = False

        non_rejected = [o for o in enriched_list if not _is_rejected(o) and not _is_hard_blocked(o)]

        if non_rejected:
            if chosen_id and str(chosen_id) in enriched_by_id:
                cand = enriched_by_id[str(chosen_id)]
                if (not _is_hard_blocked(cand)) and (not _is_rejected(cand)) and _get_score(cand) >= SCORE_THRESHOLDS["normal_min"]:
                    chosen = cand

            if chosen is None:
                chosen = _select_best_candidate(
                    non_rejected,
                    min_score=SCORE_THRESHOLDS["normal_min"],
                    allow_rejected=False,
                )

        if chosen is None:
            logger.warning("DebateOS: Entering degraded mode")
            all_rejected = True
            mode = DebateMode.DEGRADED
            chosen = _create_degraded_choice(enriched_list)

        if chosen is None:
            logger.error("DebateOS: No selectable candidate -> safe fallback")
            return _fallback_debate(base_options)

        # ============================
        # 最後の安全弁（ここで事故を止める）
        # ============================
        if _is_hard_blocked(chosen):
            logger.error("DebateOS: Chosen is hard-blocked -> safe fallback")
            return _fallback_debate(base_options)

        if _looks_dangerous_text(chosen):
            logger.error("DebateOS: Chosen looks dangerous -> safe fallback")
            fb = _fallback_debate(base_options)
            fb["warnings"] = (fb.get("warnings") or []) + ["⚠️ 安全弁: 危険な可能性がある候補を検出したため safe_fallback に切替"]
            return fb

        if mode == DebateMode.DEGRADED and _get_score(chosen) < SCORE_THRESHOLDS["degraded_min"]:
            logger.error("DebateOS: Degraded chosen below degraded_min -> safe fallback")
            fb = _fallback_debate(base_options)
            fb["warnings"] = (fb.get("warnings") or []) + ["⚠️ 安全弁: degraded_min 未満のため safe_fallback に切替"]
            return fb

        risk_delta = _calc_risk_delta(chosen, enriched_list)
        summary = _build_debate_summary(chosen, enriched_list, mode)
        warning_msg = _create_warning_message(chosen, mode, all_rejected)
        warnings = [w for w in warning_msg.split("\n") if w.strip()]

        logger.info(
            "DebateOS: Selected id=%s title=%s score=%.2f verdict=%s mode=%s",
            chosen.get("id"),
            chosen.get("title"),
            _get_score(chosen),
            _normalize_verdict_by_score(chosen),
            mode,
        )

        return {
            "chosen": chosen,
            "options": enriched_list,
            "raw": parsed,
            "source": "openai_llm",
            "mode": mode,
            "risk_delta": risk_delta,
            "warnings": warnings,
            "debate_summary": summary,
            "meta": {
                "thresholds": SCORE_THRESHOLDS,
                "chosen_id_from_llm": chosen_id,
                "safety_valve": "on",
            },
        }

    except Exception as e:
        logger.error("DebateOS: LLM call or parse failed: %r", e)
        return _fallback_debate(base_options)


