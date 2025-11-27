# veritas_os/scripts/generate_consistency_certificate.py
from __future__ import annotations

import json
import os
import runpy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict

try:
    # 既存の LOG_DIR 設定をそのまま利用
    from veritas_os.logging.paths import LOG_DIR
except Exception:
    # 念のためのフォールバック（プロジェクト直下の scripts/logs）
    BASE_DIR = Path(__file__).resolve().parents[2]
    LOG_DIR = str(BASE_DIR / "veritas_os" / "scripts" / "logs")

LOG_PATH = Path(LOG_DIR)
REPORT_PATH = LOG_PATH / "doctor_report.json"
WORLD_STATE_PATH = LOG_PATH / "world_state.json"
CERT_PATH = LOG_PATH / "consistency_certificate.json"

# ★ trust_log の候補パス（どれか1つあればそれを使う）
TRUSTLOG_CANDIDATES = [
    LOG_PATH / "trust_log.json1",
    LOG_PATH / "trust_log.jsonl",
    LOG_PATH / "trust_log.json",
]

def _pick_trustlog_path() -> Path | None:
    for p in TRUSTLOG_CANDIDATES:
        if p.exists():
            return p
    return TRUSTLOG_CANDIDATES[0]  # どれも無ければ最初をデフォルトとして返す

TRUSTLOG_PATH = _pick_trustlog_path()


# ---------- small utils ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[certificate] JSON load error for {path}: {e}")
        return None


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- trust_log チェック（verify_trust_log.py を再利用） ----------

def _verify_trust_log() -> bool:
    """
    veritas_os.scripts.verify_trust_log を __main__ として実行し、
    例外なく終了したら OK とみなす。

    ※ print はそのまま流れる（監査ログとして許容）
    """
    if not TRUSTLOG_PATH.exists():
        print(f"[certificate] trust_log file not found: {TRUSTLOG_PATH}")
        return False

    try:
        runpy.run_module("veritas_os.scripts.verify_trust_log", 
run_name="__main__")
        return True
    except SystemExit as e:
        code = getattr(e, "code", 0)
        print(f"[certificate] verify_trust_log exited with code={code}")
        return code == 0
    except Exception as e:
        print(f"[certificate] verify_trust_log error: {e!r}")
        return False


# ---------- main ----------

def generate_certificate() -> Dict[str, Any]:
    LOG_PATH.mkdir(parents=True, exist_ok=True)

    doctor = _load_json(REPORT_PATH)
    world_state = _load_json(WORLD_STATE_PATH)

    doctor_ok = isinstance(doctor, dict)
    world_ok = isinstance(world_state, dict)

    trust_ok = _verify_trust_log()

    veritas_version = os.getenv("VERITAS_VERSION", "1.0.0")

    cert: Dict[str, Any] = {
        "generated_at": _now_iso(),
        "veritas_version": veritas_version,
        "checks": {
            "doctor_report_present": doctor_ok,
            "trust_log_verified": trust_ok,
            "world_state_present": world_ok,
        },
        "files": {
            "doctor_report": {
                "path": str(REPORT_PATH),
                "exists": REPORT_PATH.exists(),
                "sha256": _file_sha256(REPORT_PATH),
            },
            "trust_log_json1": {
                "path": str(TRUSTLOG_PATH),
                "exists": TRUSTLOG_PATH.exists(),
                "sha256": _file_sha256(TRUSTLOG_PATH),
            },
            "world_state": {
                "path": str(WORLD_STATE_PATH),
                "exists": WORLD_STATE_PATH.exists(),
                "sha256": _file_sha256(WORLD_STATE_PATH),
            },
        },
        "meta": {
            "source_dir": str(LOG_PATH),
            "note": (
                "This certificate only reflects local log inspection "
                "at the time of generation. It is not a remote attestation."
            ),
        },
    }

    with CERT_PATH.open("w", encoding="utf-8") as f:
        json.dump(cert, f, ensure_ascii=False, indent=2)

    print(f"[certificate] consistency_certificate.json written to {CERT_PATH}")
    return cert


if __name__ == "__main__":
    generate_certificate()
