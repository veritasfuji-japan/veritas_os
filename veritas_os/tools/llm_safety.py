# veritas_os/tools/llm_safety.py
# -*- coding: utf-8 -*-
"""
llm_safety tool

FUJI Gate から呼ばれる「安全ヘッド」。
- 可能なら OpenAI などの LLM を使って安全判定
- 使えない場合はローカルの簡易ヒューリスティックにフォールバック

戻り値フォーマット（fuji.run_safety_head からの期待値）:

{
  "ok": True,
  "risk_score": 0.23,              # 0〜1
  "categories": ["PII", "illicit"],
  "rationale": "短い理由文",
  "model": "gpt-4.1-mini",
  "raw": {...}                     # モデル生出力 or 追加情報
}
"""

from __future__ import annotations
import importlib.util
from typing import Any, Dict, List
import json
import logging
import math
import os
import re
import time
import unicodedata

logger = logging.getLogger(__name__)

if importlib.util.find_spec("openai") is not None:  # pragma: no cover
    from openai import OpenAI  # type: ignore
else:  # pragma: no cover
    OpenAI = None  # type: ignore


# -------------------------------
# ヒューリスティック用キーワード（Deterministic Safety Layer）
# セキュリティ監査 2026-03-12 F-02 対応: パターン数を大幅拡充
# -------------------------------
# --- English single-word keywords: matched with word boundaries to avoid
#     false positives (e.g. "kill" in "skill", "harm" in "pharmacy"). ---
_BANNED_EN_WORDS: set[str] = {
    # violence / harm
    "harm", "kill", "murder", "assassinate", "attack", "shoot", "stab",
    "strangle", "torture", "kidnap", "abduct",
    # weapons
    "weapon", "bomb", "explosive", "firearm", "grenade", "landmine",
    "ammunition", "detonator",
    # cyber / hacking
    "exploit", "malware", "ransomware", "trojan", "rootkit", "keylogger",
    "botnet", "ddos", "phishing", "spyware",
    # illegal
    "illegal", "doxx", "trafficking", "smuggling", "counterfeit",
    "fraud", "extortion", "blackmail", "bribery",
}
# --- English multi-word phrases: safe for substring matching ---
_BANNED_EN_PHRASES: set[str] = {
    "money laundering", "drug synthesis", "methamphetamine", "fentanyl",
    "cocaine synthesis", "heroin synthesis",
    "child exploitation", "csam", "child pornography",
}
# --- Japanese keywords: substring matching is correct for Japanese ---
_BANNED_JP: set[str] = {
    # violence
    "毒", "殺", "殺害", "暗殺", "拷問", "誘拐", "襲撃",
    # weapons
    "爆弾", "銃", "兵器", "火器", "手榴弾", "地雷", "弾薬",
    # cyber
    "ハッキング", "マルウェア", "ランサムウェア", "トロイの木馬",
    "キーロガー", "ボットネット", "フィッシング", "スパイウェア",
    # illegal
    "違法", "人身売買", "密売", "密輸", "偽造", "資金洗浄",
    "詐欺", "恐喝", "脅迫", "贈賄",
    # CSAM
    "児童ポルノ", "児童搾取",
}

_SENSITIVE_EN_WORDS: set[str] = {
    "pathogen", "ricin", "anthrax", "sarin", "plutonium", "lockpick",
}
_SENSITIVE_EN_PHRASES: set[str] = {
    "drug synthesis", "zero-day", "unlock jail",
    "nerve agent", "chemical weapon", "biological weapon",
    "uranium enrichment",
    "social engineering attack", "privilege escalation",
    "sql injection", "remote code execution", "buffer overflow",
    "self-harm", "suicide method", "how to die",
}
_SENSITIVE_JP: set[str] = {
    "生物兵器", "毒物合成", "ゼロデイ", "脱獄", "暗号回避",
    "神経ガス", "化学兵器", "リシン", "炭疽菌", "サリン",
    "プルトニウム", "ウラン濃縮",
    "権限昇格", "SQLインジェクション", "リモートコード実行",
    "自傷", "自殺方法",
}

# Compiled word-boundary regexes for English single words (built once at import)
_BANNED_EN_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_BANNED_EN_WORDS)) + r")\b",
    re.IGNORECASE,
)
_SENSITIVE_EN_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(_SENSITIVE_EN_WORDS)) + r")\b",
    re.IGNORECASE,
)

# Regex-based compound patterns for detecting obfuscated / paraphrased threats
_COMPOUND_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # (compiled_regex, category, label)
    (re.compile(r"how\s+to\s+(make|build|create|synthesize)\s+.{0,30}(bomb|explosive|weapon|poison|drug|meth)", re.IGNORECASE),
     "illicit", "synthesis_instructions"),
    (re.compile(r"(make|build|create)\s+.{0,20}(pipe\s*bomb|molotov|ied|improvised)", re.IGNORECASE),
     "illicit", "weapon_construction"),
    (re.compile(r"(hack|crack|break\s+into)\s+.{0,30}(account|server|system|network|password)", re.IGNORECASE),
     "illicit", "hacking_instructions"),
    (re.compile(r"(buy|purchase|obtain|get)\s+.{0,20}(illegal|stolen|fake|forged)\s+.{0,20}(id|passport|license|credit\s*card)", re.IGNORECASE),
     "illicit", "illegal_procurement"),
    (re.compile(r"(suicide|kill\s+myself|end\s+my\s+life|ways?\s+to\s+die)", re.IGNORECASE),
     "self_harm", "self_harm_intent"),
    (re.compile(r"(cut|hurt|injure)\s+(myself|yourself|themselves)", re.IGNORECASE),
     "self_harm", "self_harm_action"),
    (re.compile(r"(作り方|製造法|合成法|調合).{0,10}(爆弾|毒|薬物|覚醒剤|麻薬)"),
     "illicit", "synthesis_instructions_jp"),
    (re.compile(r"(ハック|クラック|侵入|不正アクセス).{0,15}(サーバ|システム|アカウント|パスワード)"),
     "illicit", "hacking_instructions_jp"),
    (re.compile(r"(自殺|死にたい|死に方|命を絶つ)"),
     "self_harm", "self_harm_intent_jp"),
]

_RE_PHONE  = re.compile(r'(0\d{1,4}[-―‐ｰ–—]?\d{1,4}[-―‐ｰ–—]?\d{3,4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
_RE_ADDRJP = re.compile(r'([都道府県]|市|区|町|村).{0,20}\d')
# ★ 修正: 漢字2〜4文字だけでは日本語テキスト全般にマッチして偽陽性が多すぎるため、
# 敬称（さん/様/氏/先生/殿）付きの名前パターンに限定する（sanitize.py と同様のアプローチ）
# 例: "山田太郎さん", "田中 様", "鈴木先生"
_RE_NAMEJP = re.compile(r'[\u4e00-\u9fff]{2,4}\s*(?:さん|様|氏|先生|殿)')
_RE_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_PROMPT_TEXT_CHARS = 8000
_LEETSPEAK_TRANSLATION = str.maketrans(
    {
        "0": "o",
        "1": "i",
        "3": "e",
        "4": "a",
        "5": "s",
        "7": "t",
        "8": "b",
        "9": "g",
        "@": "a",
        "$": "s",
        "!": "i",
    }
)


def _sanitize_text_for_prompt(text: str, max_chars: int = _MAX_PROMPT_TEXT_CHARS) -> str:
    """LLM へ渡すユーザー入力をプロンプト安全な文字列に正規化する。

    - 制御文字を除去して、改行・タブなどを空白へ圧縮する
    - 過大入力によるプロンプト汚染やコスト増を防ぐため文字数を上限制限する

    Args:
        text: ユーザー入力。
        max_chars: 文字数上限（0 以下は 1 として扱う）。

    Returns:
        安全化済みの文字列。
    """
    safe_limit = max(1, int(max_chars))
    cleaned = _RE_CONTROL_CHARS.sub(" ", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:safe_limit]


def normalize_text(s: str) -> str:
    """Normalize text with NFKC Unicode normalization for confusable character detection."""
    t = unicodedata.normalize("NFKC", s or "")
    return t.replace("　", " ").strip().casefold()


# 後方互換エイリアス（テスト移行期間中に維持）
_norm = normalize_text


def _build_safety_scan_variants(text: str) -> list[str]:
    """Build obfuscation-resistant variants for deterministic safety scanning.

    The first element is always the canonical NFKC-normalized text. Extra
    variants target adversarial prompts such as ``k1ll``, ``k.i.l.l``, and
    character-spaced keywords.

    Args:
        text: User supplied content.

    Returns:
        Ordered unique variants used by keyword and regex checks.
    """
    base = _norm(text)
    variants: list[str] = [base]

    leet = base.translate(_LEETSPEAK_TRANSLATION)
    if leet not in variants:
        variants.append(leet)

    compact = re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+", "", leet)
    if compact and compact not in variants:
        variants.append(compact)

    return variants


def _normalize_categories(categories: list[Any], max_categories: int) -> list[str]:
    """LLM が返すカテゴリ配列を監査しやすい安全な形式へ正規化する。

    Args:
        categories: LLM レスポンス上のカテゴリ配列。
        max_categories: 返却上限。0 以下は 0 扱い。

    Returns:
        重複除去済み・トリム済み・長さ制限済み・制御文字除去済みのカテゴリ一覧。
    """
    safe_limit = max(0, int(max_categories))
    if safe_limit == 0:
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for raw in categories:
        category = str(raw).strip()
        if not category:
            continue
        category = _RE_CONTROL_CHARS.sub("", category)
        category = re.sub(r"\s+", " ", category).strip()
        if not category:
            continue
        # 監査ログ肥大化を避けるため、カテゴリ1件あたりの長さを制限
        category = category[:64]
        dedupe_key = category.casefold()
        if dedupe_key in seen:
            continue
        normalized.append(category)
        seen.add(dedupe_key)
        if len(normalized) >= safe_limit:
            break

    return normalized


def heuristic_analyze(text: str) -> Dict[str, Any]:
    """Deterministic safety analysis (always runs, LLM-independent).

    セキュリティ監査 2026-03-12 F-01/F-02 対応:
    - Unicode NFKC 正規化後にマッチング
    - 拡充されたキーワードセット（数百パターン）
    - 正規表現ベースの複合パターンマッチ
    - カテゴリ別リスク設定
    """
    scan_variants = _build_safety_scan_variants(text)
    t = scan_variants[0]
    categories: List[str] = []
    risk = 0.05
    reasons: List[str] = []

    # --- Keyword matching (NFKC-normalized, casefold) ---
    # English single words: word-boundary regex to avoid false positives
    hits_b: List[str] = []
    hits_s: List[str] = []
    for variant in scan_variants:
        hits_b += _BANNED_EN_WORD_RE.findall(variant)
        # English multi-word phrases + Japanese: substring match (safe)
        hits_b += [w for w in _BANNED_EN_PHRASES if w in variant]
        hits_b += [w for w in _BANNED_JP if w in variant]

        hits_s += _SENSITIVE_EN_WORD_RE.findall(variant)
        hits_s += [w for w in _SENSITIVE_EN_PHRASES if w in variant]
        hits_s += [w for w in _SENSITIVE_JP if w in variant]

    if hits_b or hits_s:
        categories.append("illicit")
        risk = max(risk, 0.8)
        reasons.append(
            f"危険/違法寄りワード検出: {', '.join(sorted(set(hits_b + hits_s)))}"
        )

    # --- Compound regex pattern matching ---
    # Always search the NFKC-normalized text to ensure consistent matching
    compound_hits: List[str] = []
    for pattern, cat, label in _COMPOUND_PATTERNS:
        if pattern.search(text) or any(pattern.search(v) for v in scan_variants):
            compound_hits.append(label)
            if cat not in categories:
                categories.append(cat)
            # Initial scores kept moderate; the deterministic safety layer in
            # fuji_core_decide will apply category-specific floors and LLM
            # unavailable penalties on top of these.
            if cat == "self_harm":
                risk = max(risk, 0.75)
            else:
                risk = max(risk, 0.65)

    if compound_hits:
        reasons.append(f"複合パターン検出: {', '.join(sorted(set(compound_hits)))}")

    # --- PII detection ---
    pii_hits: List[str] = []
    if _RE_PHONE.search(text):
        pii_hits.append("phone")
    if _RE_EMAIL.search(text):
        pii_hits.append("email")
    if _RE_ADDRJP.search(text):
        pii_hits.append("address")
    if _RE_NAMEJP.search(text):
        pii_hits.append("name_like")

    if pii_hits:
        categories.append("PII")
        risk = max(risk, 0.35)
        reasons.append(f"PII パターン検出: {', '.join(pii_hits)}")

    if not categories:
        reasons.append("特に危険ワード/PII パターンは検出されませんでした。")

    return {
        "ok": True,
        "risk_score": min(1.0, risk),
        "categories": sorted(set(categories)),
        "rationale": " / ".join(reasons),
        "model": "heuristic_fallback",
        "raw": {
            "fallback": True,
            "banned_hits": hits_b + hits_s,
            "pii_hits": pii_hits,
            "compound_hits": compound_hits,
        },
    }


# 後方互換エイリアス（テスト移行期間中に維持）
_heuristic_analyze = heuristic_analyze


def _score_risk(
    *,
    llm_risk: float,
    llm_categories: List[str],
    heuristic: Dict[str, Any],
) -> Dict[str, Any]:
    """
    LLM 出力とヒューリスティックを決定論的に合成する。

    - リスクは max(llm_risk, heuristic_risk) をベースに固定ルールで補正
    - カテゴリは LLM を優先しつつ重複しない形で併合
    """
    heuristic_risk = float(heuristic.get("risk_score", 0.0) or 0.0)
    heuristic_categories = [str(c) for c in (heuristic.get("categories") or [])]

    combined_categories = list(llm_categories)
    for cat in heuristic_categories:
        if cat not in combined_categories:
            combined_categories.append(cat)

    notes: List[str] = []
    combined_risk = max(llm_risk, heuristic_risk)

    if heuristic_risk > llm_risk:
        combined_risk = min(1.0, heuristic_risk + 0.05)
        notes.append("heuristic_risk_override")

    if "illicit" in heuristic_categories and "illicit" not in llm_categories:
        combined_risk = min(1.0, max(combined_risk, 0.7))
        notes.append("illicit_floor")

    return {
        "risk_score": combined_risk,
        "categories": combined_categories,
        "heuristic_risk": heuristic_risk,
        "notes": notes,
    }


def _llm_available() -> bool:
    if OpenAI is None:
        return False
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_VERITAS")
    return bool(api_key)


def _analyze_with_llm(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """
    OpenAI Responses API などを使った「ちゃんとした安全ヘッド」。
    モデル名は VERITAS_SAFETY_MODEL で差し替え可能。
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY_VERITAS")
    if not api_key:  # 念のため再チェック
        raise RuntimeError("OPENAI_API_KEY not set for llm_safety")

    model_name = os.getenv("VERITAS_SAFETY_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    # context から stakes 等を軽く渡してあげる
    ctx = context or {}
    stakes = float(ctx.get("stakes", 0.5) or 0.5)

    system = (
        "You are a safety classification head for an AI system called VERITAS.\n"
        "Your job is ONLY to classify the RISK of a given text, NOT to answer it.\n"
        "Output a short JSON with: risk_score (0-1), categories, rationale.\n"
        "Think in terms of OpenAI-like safety categories: PII, self_harm, illicit, violence, hate, minors, etc."
    )

    sanitized_text = _sanitize_text_for_prompt(text)
    user_payload = {
        "text": sanitized_text,
        "stakes": stakes,
        "alternatives_preview": [
            a.get("title") or a.get("description") or ""
            for a in (alternatives or [])[:5]
        ],
    }

    user_content = f"CLASSIFY_THIS_INPUT:\n```json\n{json.dumps(user_payload, ensure_ascii=False)}\n```"

    t0 = time.time()

    # Responses API (.responses.create) を優先し、非対応の場合は
    # Chat Completions API (.chat.completions.create) にフォールバックする。
    # SDK バージョンや Azure ラッパーによって .responses が存在しない場合がある。
    use_responses_api = hasattr(client, "responses") and hasattr(client.responses, "create")

    if use_responses_api:
        resp = client.responses.create(
            model=model_name,
            reasoning={"effort": "low"},
            temperature=0,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "safety_head_output",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "risk_score": {"type": "number"},
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["risk_score", "categories", "rationale"],
                        "additionalProperties": True,
                    },
                    "strict": False,
                },
            },
        )
        latency_ms = int((time.time() - t0) * 1000)

        # Responses API の JSON 抜き出し
        # ★ H-5 修正: output が空の場合の IndexError を防止
        output = getattr(resp, "output", None)
        if not output or len(output) == 0:
            raise RuntimeError("LLM safety head returned empty output")
        out = getattr(output[0], "parsed", None)
        if out is None:
            raise RuntimeError("LLM safety head returned unparseable output")
    else:
        # Fallback: Chat Completions API
        logger.info("LLM safety head: .responses unavailable, using chat.completions fallback")
        resp = client.chat.completions.create(
            model=model_name,
            temperature=0,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
        )
        latency_ms = int((time.time() - t0) * 1000)

        raw_text = (resp.choices[0].message.content or "").strip() if resp.choices else ""
        if not raw_text:
            raise RuntimeError("LLM safety head returned empty chat completion")
        out = json.loads(raw_text)

    try:
        risk = float(out.get("risk_score", 0.05) or 0.05)
    except (ValueError, TypeError):
        risk = 0.05
    if not math.isfinite(risk):
        risk = 0.05
    cats = out.get("categories") or []
    rat = out.get("rationale") or ""

    heuristic = heuristic_analyze(text)
    scoring = _score_risk(
        llm_risk=risk,
        llm_categories=[str(c) for c in cats],
        heuristic=heuristic,
    )
    scored_categories = _normalize_categories(scoring["categories"], max_categories)
    scored_risk = float(scoring["risk_score"])
    scoring_notes = scoring.get("notes") or []
    if scoring_notes:
        rat = f"{rat} / scoring={'|'.join(scoring_notes)}"

    return {
        "ok": True,
        "risk_score": max(0.0, min(1.0, scored_risk)),
        "categories": scored_categories,
        "rationale": str(rat),
        "model": model_name,
        "raw": {
            "latency_ms": latency_ms,
            "scoring": {
                "llm_risk": risk,
                "heuristic_risk": scoring.get("heuristic_risk"),
                "notes": scoring_notes,
            },
            "response": resp.model_dump_json() if hasattr(resp, "model_dump_json") else str(resp),  # 監査用
        },
    }


def run(
    text: str,
    context: Dict[str, Any] | None = None,
    alternatives: List[Dict[str, Any]] | None = None,
    max_categories: int = 5,
) -> Dict[str, Any]:
    """
    call_tool("llm_safety", ...) から呼ばれるエントリポイント。
    """
    # 強制ヒューリスティックモード（テスト・オフライン用）
    if os.getenv("VERITAS_SAFETY_MODE", "").lower() in {"heuristic", "local"}:
        return heuristic_analyze(text)

    if _llm_available():
        try:
            return _analyze_with_llm(
                text=text,
                context=context,
                alternatives=alternatives,
                max_categories=max_categories,
            )
        except Exception as e:
            # LLM 失敗時は fallback — セキュリティ監査 F-01 対応:
            # fallback=True を明示し、呼び出し元が追加ペナルティを適用できるようにする
            logger.warning("LLM safety head failed, falling back to heuristic: %s: %s", type(e).__name__, e)
            fb = heuristic_analyze(text)
            fb["ok"] = False
            fb["degraded"] = True
            fb["llm_fallback"] = True
            fb.setdefault("raw", {})["llm_error"] = "LLM safety head unavailable"
            fb.setdefault("raw", {})["llm_error_type"] = type(e).__name__
            return fb

    # API キー不在など → ヒューリスティック
    # セキュリティ監査 F-04 対応: LLM 不在を明示
    fb = heuristic_analyze(text)
    fb["llm_fallback"] = True
    fb.setdefault("raw", {})["llm_unavailable"] = True
    return fb
