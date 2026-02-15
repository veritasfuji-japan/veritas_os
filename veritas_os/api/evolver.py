import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from .schemas import PersonaState
from ..core.config import cfg
from ..core.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

PERSONA_JSON = cfg.log_dir / "persona.json"


def _extract_keywords(text: str, k: int = 6) -> list[str]:
    """テキストからキーワードを抽出（長い順に最大k個）"""
    words = re.findall(r"[A-Za-z0-9\u3040-\u30FF\u4E00-\u9FFF]+", text or "")
    words = sorted(set(words), key=len, reverse=True)
    return words[:k]


def load_persona() -> dict:
    """persona.json があれば辞書で返す。無ければ空 dict。"""
    try:
        if PERSONA_JSON.exists():
            with open(PERSONA_JSON, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("[persona] load failed: %s", e)
    return {}


def save_persona(p: PersonaState) -> None:
    """PersonaStateをpersona.jsonに保存"""
    try:
        # 新しいインスタンスを作成（immutable対応）
        updated = PersonaState(
            name=p.name,
            style=p.style,
            tone=p.tone,
            principles=p.principles,
            last_updated=(
                datetime.now(UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
            ),
        )

        # ★ クラッシュセーフ: atomic_write_json で書き込み
        # write_text() は書き込み途中のクラッシュでデータ破損のリスクがある
        atomic_write_json(PERSONA_JSON, updated.model_dump(), indent=2)
    except Exception as e:
        logger.warning("[persona] save failed: %s", e)


def apply_persona(chosen: dict, persona: PersonaState) -> dict:
    """決定にペルソナメタデータを付与する。

    `_persona` キーがすでに存在していても、値が dict 以外なら
    破損データとみなして安全に上書きする。
    """
    if not chosen or not persona:
        return chosen or {}

    enriched = dict(chosen)
    current_meta = enriched.get("_persona")
    meta = current_meta if isinstance(current_meta, dict) else {}
    enriched["_persona"] = meta
    meta["name"] = persona.name
    meta["style"] = persona.style
    meta["tone"] = persona.tone
    meta["principles"] = persona.principles
    return enriched


def _resolve_uncertainty(chosen: dict[str, Any]) -> float | None:
    """Estimate uncertainty score from a decision payload.

    Priority:
    1) `uncertainty` is used directly.
    2) `confidence` is converted to uncertainty as `1 - confidence`.

    Returns None when no numeric signal is available.
    """
    if not isinstance(chosen, dict):
        return None

    raw_uncertainty = chosen.get("uncertainty")
    if raw_uncertainty is not None:
        try:
            return float(raw_uncertainty)
        except (TypeError, ValueError):
            return None

    raw_confidence = chosen.get("confidence")
    if raw_confidence is None:
        return None

    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        return None

    return 1.0 - confidence


def evolve_persona(persona: PersonaState, evo: dict) -> PersonaState:
    """キーワードに基づいてペルソナスタイルを進化"""
    if not evo or not persona:
        return persona

    kws = (evo or {}).get("insights", {}).get("keywords", [])

    # 研究/実証系キーワードでスタイル進化
    if any(k in kws for k in ["研究", "実証", "検証"]) and "evidence-first" not in persona.style:
        # 新しいインスタンスを返す（immutable対応）
        return PersonaState(
            name=persona.name,
            style=persona.style + ", evidence-first",
            tone=persona.tone,
            principles=persona.principles,
            last_updated=persona.last_updated,
        )

    return persona


def generate_suggestions(
    query: str,
    chosen: dict[str, Any],
    alts: list[dict[str, Any]],
) -> dict[str, Any]:
    """決定後の行動提案とフォローアップを生成する。

    `uncertainty` が無い場合は `confidence` を uncertainty に変換して
    追加検証アクションの要否を判定する。
    """
    text = (chosen or {}).get("text") or (chosen or {}).get("answer") or ""
    kws = _extract_keywords((query or "") + " " + text, k=6)

    actions: list[str] = []
    next_prompts: list[str] = []
    notes: list[str] = []

    # 不確実性チェック
    uncertainty = _resolve_uncertainty(chosen or {})
    if uncertainty is not None and uncertainty > 0.6:
        actions.append("一次情報(ソースURL)を1件以上添付する")
        next_prompts.append("この結論の一次情報(最も信頼できる根拠)は？")

    # 代替案統合提案
    if alts:
        actions.append("代替案の強みだけを統合して最適案を作る")
        next_prompts.append("代替案の強みだけを統合した最適案を出して")

    # 最小ステップ提案
    actions.append("30分で検証できる最小ステップに分解して着手")
    next_prompts.append("このテーマを30分で検証する最小ステップは？")

    return {
        "insights": {"keywords": kws},
        "actions": actions,
        "next_prompts": next_prompts,
        "notes": notes,
    }
