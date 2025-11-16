# veritas/core/reflection.py (新規)
def evaluate_decision(decision, outcome, memory):
    score = trust_log.evaluate(decision, outcome)
    if score < 0.5:
        ValueCore.adjust_weights("prudence", +0.1)
    memory.append({"decision_id": decision.id, "score": 
score})
    return score
