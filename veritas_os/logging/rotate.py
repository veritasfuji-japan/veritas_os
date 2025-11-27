import os
from .paths import LOG_DIR

TRUST_LOG = os.path.join(LOG_DIR, "trust_log.jsonl")
MAX_LINES = 5000

def count_lines(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)

def rotate_if_needed():
    lines = count_lines(TRUST_LOG)
    if lines < MAX_LINES:
        return TRUST_LOG

    # rotate
    base = TRUST_LOG.replace(".jsonl", "")
    rotated = base + "_old.jsonl"
    if os.path.exists(rotated):
        os.remove(rotated)
    os.rename(TRUST_LOG, rotated)

    return TRUST_LOG

def open_trust_log_for_append():
    rotate_if_needed()
    return open(TRUST_LOG, "a", encoding="utf-8")
