def propose_patch(last_outcome: dict) -> dict:
    # 例：evidenceの閾値を上げる／批判の重みを微増
    return {"min_evidence_delta": +1, "critique_weight_delta": +0.1}

def validate_and_apply(patch: dict, state: dict) -> dict:
    # FUJIや一貫性の簡易確認 → kernel設定を更新
    state.setdefault("kernel", {})
    k = state["kernel"]
    k["min_evidence"] = max(2, k.get("min_evidence",2) + patch.get("min_evidence_delta",0))
    k["critique_weight"] = round(k.get("critique_weight",1.0) + patch.get("critique_weight_delta",0.0), 2)
    return state
