import json
import pathlib

REPO_ROOT = Path(__file__).resolve().parents[2]          # .../veritas_clean_test2/veritas_os
SCRIPTS_DIR = REPO_ROOT / "scripts"                      # .../veritas_os/scripts
OUT_PATH = SCRIPTS_DIR / "logs" / "trust_log.json"       # .../veritas_os/scripts/logs/trust_log.json

def load_any_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
            if text.startswith("{") and '"items"' in text:
                return json.loads(text).get("items", [])
            else:
                items = []
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except:
                        pass
                return items
    except Exception as e:
        print("skip", path, e)
        return []

def main():
    uniq = {}

    for src in SRC_FILES:
        if not src.exists():
            continue
        for it in load_any_json(src):
            rid = it.get("request_id")
            if rid:
                uniq[rid] = it

    items = list(uniq.values())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print("merged ->", OUT_PATH, "lines:", len(items))

if __name__ == "__main__":
    main()
