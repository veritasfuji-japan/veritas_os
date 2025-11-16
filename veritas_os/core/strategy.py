from typing import List, Dict

DEFAULT_OPTIONS = [
    {"id":"A","title":"Conservative Plan","description":"安全・根拠重視で段階導入"},
    {"id":"B","title":"Balanced Plan","description":"価値/速度/安全のバランス"},
    {"id":"C","title":"Aggressive Plan","description":"高リスク高リターン"}
]

def generate_options(state: dict, ctx: dict, base: list[dict]=None) -> list[dict]:
    if base and len(base)>0:
        return [o.model_dump() if hasattr(o,"model_dump") else dict(o) for o in base]
    return DEFAULT_OPTIONS

def rank(options: List[Dict]) -> Dict:
    # デモ：A/B/Cにスコア割り当て、Bを推し
    score = {"A":0.78, "B":0.82, "C":0.60}
    best = max(options, key=lambda o: score.get(o.get("id") or "", 0.5))
    return best
