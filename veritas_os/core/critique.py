from typing import List, Dict

def analyze(option: Dict, evidence: List[Dict], context: Dict) -> List[Dict]:
    crit = []
    if len(evidence) < 2:
        crit.append({
            "issue": "根拠不足",
            "severity": "med",
            "fix": "min_evidenceを引き上げる or 追加で情報収集する"
        })
    crit.append({
        "issue": "過大スコープ",
        "severity": "med",
        "fix": "1価値 = 1画面でPoC分割"
    })
    return crit
