from typing import Any, Dict, List
import re
from pathlib import Path   
import json
from datetime import datetime  # ← FIX: datetime インポート追加
from .schemas import PersonaState
from ..core.config import cfg

PERSONA_JSON = cfg.log_dir / "persona.json"

def _extract_keywords(text: str, k: int = 6) -> List[str]:
    """テキストからキーワードを抽出（長い順に最大k個）"""
    words = re.findall(r"[A-Za-z0-9\u3040-\u30FF\u4E00-\u9FFF]+", text or "")
    words = sorted(set(words), key=len, reverse=True)
    return words[:k]


def load_persona() -> dict:
    """persona.json があれば辞書で返す。無ければ空 dict。"""
    try:
        if PERSONA_JSON.exists():
            with open(PERSONA_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print("[persona] load failed:", e)
    return {}


def save_persona(p: PersonaState) -> None:
    """PersonaStateをpersona.jsonに保存"""
    try:
        # FIX: 新しいインスタンスを作成（immutable対応）
        updated = PersonaState(
            name=p.name,
            style=p.style,
            tone=p.tone,
            principles=p.principles,
            last_updated=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        
        # ディレクトリが存在しない場合は作成
        PERSONA_JSON.parent.mkdir(parents=True, exist_ok=True)
        
        PERSONA_JSON.write_text(
            json.dumps(updated.dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[persona] save failed: {e}")


def apply_persona(chosen: dict, persona: PersonaState) -> dict:
    """決定にペルソナメタデータを付与"""
    if not chosen or not persona:
        return chosen or {}
    
    enriched = dict(chosen)
    meta = enriched.setdefault("_persona", {})
    meta["name"] = persona.name
    meta["style"] = persona.style
    meta["tone"] = persona.tone
    meta["principles"] = persona.principles
    return enriched


def evolve_persona(persona: PersonaState, evo: dict) -> PersonaState:
    """キーワードに基づいてペルソナスタイルを進化"""
    if not evo or not persona:
        return persona
    
    kws = (evo or {}).get("insights", {}).get("keywords", [])
    
    # 研究/実証系キーワードでスタイル進化
    if any(k in kws for k in ["研究", "実証", "検証"]):
        if "evidence-first" not in persona.style:
            # FIX: 新しいインスタンスを返す（immutable対応）
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
    alts: list[dict[str, Any]]
) -> dict[str, Any]:
    """決定後の行動提案とフォローアップを生成"""
    text = (chosen or {}).get("text") or (chosen or {}).get("answer") or ""
    kws = _extract_keywords((query or "") + " " + text, k=6)

    actions: list[str] = []
    next_prompts: list[str] = []
    notes: list[str] = []

    # 不確実性チェック
    unc = (chosen or {}).get("uncertainty") or (chosen or {}).get("confidence")
    try:
        if unc is not None and float(unc) > 0.6:
            actions.append("一次情報(ソースURL)を1件以上添付する")
            next_prompts.append("この結論の一次情報(最も信頼できる根拠)は？")
    except (ValueError, TypeError):
        pass

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
