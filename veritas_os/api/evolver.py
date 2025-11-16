from typing import Any, Dict, List
import re
from pathlib import Path   
import json
from .schemas import PersonaState
from ..core.config import cfg

PERSONA_JSON = cfg.log_dir / "persona.json"

def _extract_keywords(text: str, k: int = 6) -> List[str]:
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
    p.last_updated = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    PERSONA_JSON.write_text(json.dumps(p.dict(), ensure_ascii=False, indent=2), encoding="utf-8")

def apply_persona(chosen: dict, persona: PersonaState) -> dict:
    # 最小適用：style/toneを付与（必要なら言い回し変換などを拡張）
    enriched = dict(chosen or {})
    meta = enriched.setdefault("_persona", {})
    meta["name"] = persona.name
    meta["style"] = persona.style
    meta["tone"] = persona.tone
    meta["principles"] = persona.principles
    return enriched

def evolve_persona(persona: PersonaState, evo: dict) -> PersonaState:
    # キーワードから style のニュアンスを少し寄せる（超軽量）
    kws = (evo or {}).get("insights", {}).get("keywords", [])
    if any(k in kws for k in ["研究", "実証", "検証"]):
        if "evidence-first" not in persona.style:
            persona.style += ", evidence-first"
    return persona
def generate_suggestions(
    query: str,
    chosen:  dict[str, Any],
    alts: list[dict[str, Any]]
) -> dict[str, Any]:
    text = (chosen or {}).get("text") or (chosen or {}).get("answer") or ""
    kws = _extract_keywords((query or "") + " " + text, k=6)

    actions: list[str] = []
    next_prompts: list[str] = []
    notes: list[str] = []

    unc = (chosen or {}).get("uncertainty") or (chosen or {}).get("confidence")

    try:
        if unc is not None and float(unc) > 0.6:
            actions.append("一次情報(ソースURL)を1件以上添付する")
            next_prompts.append("この結論の一次情報(最も信頼できる根拠)は？")
    except Exception:
        pass

    if alts:
        actions.append("代替案の強みだけを統合して最適案を作る")
        next_prompts.append("代替案の“強みだけ”を統合した最適案を出して")

    actions.append("30分で検証できる最小ステップに分解して着手")
    next_prompts.append("このテーマを30分で検証する最小ステップは？")

    return {
        "insights": {"keywords": kws},
        "actions": actions,
        "next_prompts": next_prompts,
        "notes": notes,
    }
