# scripts/verify_trust_log.py（例）

import json
from pathlib import Path
from veritas_os.logging.paths import LOG_DIR
from veritas_os.logging.trust_log import _compute_sha256   
 #既に作ったやつを再利用

LOG_JSONL = LOG_DIR / "trust_log.jsonl"

def iter_entries():
    with open(LOG_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

def main():
    prev_hash = None
    for i, entry in enumerate(iter_entries(), 1):
        sha_prev = entry.get("sha256_prev")
        sha_self = entry.get("sha256")

        # prev チェック
        if sha_prev != prev_hash:
            print(f"[NG] line {i}: sha256_prev mismatch (expected={prev_hash}, got={sha_prev})")
            return

        # 自分自身の hash 検証
        payload = dict(entry)
        payload.pop("sha256", None)
        calc = _compute_sha256(payload)
        if calc != sha_self:
            print(f"[NG] line {i}: sha256 invalid (expected={calc}, got={sha_self})")
            return

        prev_hash = sha_self

    print("[OK] trust_log.jsonl: all entries valid")

if __name__ == "__main__":
    main()
