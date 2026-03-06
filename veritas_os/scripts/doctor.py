#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""VERITAS Doctor (enhanced with TrustLog validation)
veritas_os/scripts/logs 配下のログを解析して、
同じフォルダに doctor_report.json を出力する。

v2.0 新機能:
- TrustLog ハッシュチェーン検証
- より詳細な診断情報
"""

import os
import json
import glob
import hashlib
import statistics
from pathlib import Path
from datetime import datetime

# ==== パス定義 ====
# doctor.py の場所: veritas_os/scripts/doctor.py を想定
HERE = Path(__file__).resolve().parent          # .../veritas_os/scripts
REPO_ROOT = HERE.parent                         # .../veritas_os

# ログ置き場（decide_*.json, health_*.json など）
LOG_DIR = HERE / "logs"                         # .../veritas_os/scripts/logs
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ベンチマーク結果置き場（P2-2: 精度モニタリング）
BENCH_DIR = REPO_ROOT / "benchmarks" / "results"

# 監査用 JSONL
TRUST_LOG_JSON = LOG_DIR / "trust_log.jsonl"
LOG_JSONL = TRUST_LOG_JSON  # 互換のための別名

# ダッシュボード用レポート出力先
REPORT_PATH = LOG_DIR / "doctor_report.json"

# 解析対象パターン（JSONL優先／重複除去）
PATTERNS = [
    "decide_*.jsonl", "health_*.jsonl", "*status*.jsonl", "*.jsonl",
    "decide_*.json",  "health_*.json",  "*status*.json",
]

# キーワード辞書（必要に応じて増やしてOK）
KW_LIST = ["交渉", "天気", "疲れ", "音楽", "VERITAS"]

# ★ CPU/OOM対策: JSON解析時の安全制限
MAX_FILE_SIZE = 50 * 1024 * 1024      # 50MB: これを超えるファイルはスキップ
MAX_ITEMS_PER_FILE = 100_000          # 1ファイルあたりの最大アイテム数
MAX_TRUSTLOG_LINES = 500_000          # TrustLog検証の最大行数


# ---- TrustLog validation -------------------------------------------
def compute_hash_for_entry(prev_hash: str | None, entry: dict) -> str:
    """
    論文の式に従ったハッシュ計算: hₜ = SHA256(hₜ₋₁ || rₜ)
    
    Args:
        prev_hash: 直前のハッシュ値 (hₜ₋₁)
        entry: 現在のエントリ (rₜ)
    
    Returns:
        計算されたハッシュ値 (hₜ)
    """
    # エントリをコピーして、sha256とsha256_prevを除外
    payload = dict(entry)
    payload.pop("sha256", None)
    payload.pop("sha256_prev", None)
    
    # rₜ を JSON化（キーをソートして一意性を保証）
    entry_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    
    # hₜ₋₁ || rₜ を結合
    if prev_hash:
        combined = prev_hash + entry_json
    else:
        # 最初のエントリの場合は rₜ のみ
        combined = entry_json
    
    # SHA-256計算
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def analyze_trustlog() -> dict:
    """
    TrustLog (trust_log.jsonl) のハッシュチェーン検証
    
    Returns:
        {
            "status": "✅ 正常" | "⚠️ チェーン破損" | "not_found",
            "entries": int,
            "chain_valid": bool | None,
            "chain_breaks": int,
            "first_break": dict | None,
            "hash_mismatches": int,
            "first_mismatch": dict | None,
            "last_hash": str | None,
            "created_at": str | None,
        }
    """
    if not TRUST_LOG_JSON.exists():
        return {
            "status": "not_found",
            "entries": 0,
            "chain_valid": None,
            "chain_breaks": 0,
            "hash_mismatches": 0,
            "first_break": None,
            "first_mismatch": None,
            "last_hash": None,
            "created_at": None,
        }
    
    # ★ CPU/OOM対策: ファイルサイズチェック
    try:
        file_size = TRUST_LOG_JSON.stat().st_size
        if file_size > MAX_FILE_SIZE:
            return {
                "status": f"skipped: file too large ({file_size} bytes)",
                "entries": 0,
                "chain_valid": None,
                "chain_breaks": 0,
                "hash_mismatches": 0,
                "first_break": None,
                "first_mismatch": None,
                "last_hash": None,
                "created_at": None,
            }
    except OSError:
        pass

    total_entries = 0
    chain_valid = True
    chain_breaks = []
    hash_mismatches = []
    prev_hash = None
    last_hash = None
    last_created_at = None
    
    try:
        with open(TRUST_LOG_JSON, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                # ★ CPU対策: 行数上限チェック
                if i > MAX_TRUSTLOG_LINES:
                    break
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    total_entries += 1
                    
                    sha_prev = entry.get("sha256_prev")
                    sha_self = entry.get("sha256")
                    
                    # 1. チェーン連続性の検証
                    if sha_prev != prev_hash:
                        chain_valid = False
                        chain_breaks.append({
                            "line": i,
                            "expected_prev": prev_hash,
                            "actual_prev": sha_prev,
                            "request_id": entry.get("request_id", "unknown"),
                        })
                    
                    # 2. ハッシュ値の検証（論文の式に従う）
                    calc_hash = compute_hash_for_entry(sha_prev, entry)
                    if calc_hash != sha_self:
                        chain_valid = False
                        hash_mismatches.append({
                            "line": i,
                            "expected_hash": calc_hash[:16] + "...",
                            "actual_hash": (sha_self[:16] + "...") if sha_self else None,
                            "request_id": entry.get("request_id", "unknown"),
                        })
                    
                    prev_hash = sha_self
                    last_hash = sha_self
                    
                    # 最終作成日時を記録
                    if "created_at" in entry:
                        last_created_at = entry["created_at"]
                    
                except json.JSONDecodeError:
                    # 破損行は無視して続行
                    continue
    
    except Exception as e:
        return {
            "status": f"error: {str(e)}",
            "entries": 0,
            "chain_valid": False,
            "chain_breaks": 0,
            "hash_mismatches": 0,
            "first_break": None,
            "first_mismatch": None,
            "last_hash": None,
            "created_at": None,
        }
    
    # ステータス判定
    if total_entries == 0:
        status = "empty"
    elif chain_valid:
        status = "✅ 正常"
    else:
        status = "⚠️ チェーン破損"
    
    return {
        "status": status,
        "entries": total_entries,
        "chain_valid": chain_valid,
        "chain_breaks": len(chain_breaks),
        "hash_mismatches": len(hash_mismatches),
        "first_break": chain_breaks[0] if chain_breaks else None,
        "first_mismatch": hash_mismatches[0] if hash_mismatches else None,
        "last_hash": last_hash[:16] + "..." if last_hash else None,
        "created_at": last_created_at,
    }


# ---- P2-2: Accuracy monitoring dashboard ---------------------------------
def analyze_accuracy_benchmarks() -> dict:
    """Analyse benchmark result files for accuracy monitoring (P2-2 / Art. 15).

    Scans ``BENCH_DIR`` for JSON/JSONL result files and computes aggregate
    accuracy metrics.  This powers the continuous accuracy monitoring
    dashboard referenced in the EU AI Act compliance review.

    Returns:
        {
            "status": str,
            "total_runs": int,
            "latest_run": dict | None,
            "accuracy_avg": float | None,
            "accuracy_min": float | None,
            "accuracy_max": float | None,
            "drift_detected": bool,
            "drift_details": str | None,
            "benchmark_files": int,
        }
    """
    if not BENCH_DIR.exists():
        return {
            "status": "no_benchmark_dir",
            "total_runs": 0,
            "latest_run": None,
            "accuracy_avg": None,
            "accuracy_min": None,
            "accuracy_max": None,
            "drift_detected": False,
            "drift_details": None,
            "benchmark_files": 0,
        }

    bench_dir_resolved = BENCH_DIR.resolve()
    bench_files: list[str] = []
    for pat in ("*.json", "*.jsonl"):
        for p in glob.glob(os.path.join(BENCH_DIR, pat)):
            try:
                rp = Path(p).resolve()
                if bench_dir_resolved not in rp.parents and rp != bench_dir_resolved:
                    continue
                if Path(p).is_symlink() or not rp.is_file():
                    continue
                if os.path.getsize(p) <= 0 or os.path.getsize(p) > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            bench_files.append(p)

    bench_files.sort(key=lambda p: os.path.getmtime(p))

    accuracies: list[float] = []
    latest_run: dict | None = None
    total_runs = 0

    for path in bench_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Try JSONL
                data = None
                for raw_line in content.splitlines():
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        data = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

            if data is None:
                continue

            # Support both single-run and multi-run formats
            runs: list[dict] = []
            if isinstance(data, list):
                runs = [d for d in data if isinstance(d, dict)]
            elif isinstance(data, dict):
                if isinstance(data.get("runs"), list):
                    runs = [d for d in data["runs"] if isinstance(d, dict)]
                else:
                    runs = [data]

            for run in runs[:MAX_ITEMS_PER_FILE]:
                total_runs += 1
                # Accept multiple accuracy field names
                acc = (
                    run.get("accuracy")
                    or run.get("accuracy_score")
                    or run.get("score")
                )
                try:
                    if acc is not None:
                        accuracies.append(float(acc))
                except (TypeError, ValueError):
                    pass
                latest_run = run

        except Exception:
            continue

    # Drift detection: if last 5 runs show decline > 5% vs overall average
    drift_detected = False
    drift_details: str | None = None
    if len(accuracies) >= 5:
        overall_avg = statistics.mean(accuracies)
        recent_avg = statistics.mean(accuracies[-5:])
        drop = overall_avg - recent_avg
        if drop > 0.05 and overall_avg > 0:
            drift_detected = True
            drift_details = (
                f"Recent 5-run avg ({recent_avg:.3f}) dropped {drop:.3f} "
                f"from overall avg ({overall_avg:.3f})"
            )

    return {
        "status": "ok" if total_runs > 0 else "no_results",
        "total_runs": total_runs,
        "latest_run": {
            k: latest_run[k]
            for k in ("accuracy", "accuracy_score", "score", "timestamp", "benchmark", "model")
            if k in latest_run
        } if latest_run else None,
        "accuracy_avg": round(statistics.mean(accuracies), 4) if accuracies else None,
        "accuracy_min": round(min(accuracies), 4) if accuracies else None,
        "accuracy_max": round(max(accuracies), 4) if accuracies else None,
        "drift_detected": drift_detected,
        "drift_details": drift_details,
        "benchmark_files": len(bench_files),
    }


# ---- helpers -----------------------------------------------------------
def _iter_files() -> list[str]:
    """PATTERNS に一致するログの絶対パスを mtime 昇順で返す（重複除去）"""
    log_dir_resolved = LOG_DIR.resolve()

    def _is_safe_log_file(path_str: str) -> bool:
        """LOG_DIR 配下の通常ファイルのみ解析対象として許可する。"""
        try:
            path_obj = Path(path_str)
            resolved = path_obj.resolve()
        except (OSError, RuntimeError):
            return False

        if log_dir_resolved not in resolved.parents:
            return False
        if path_obj.is_symlink() or (not resolved.is_file()):
            return False
        return True

    seen, files = set(), []
    for pat in PATTERNS:
        for p in glob.glob(os.path.join(LOG_DIR, pat)):
            if p in seen or not _is_safe_log_file(p):
                continue
            try:
                if os.path.getsize(p) <= 0:
                    continue
            except OSError:
                continue
            seen.add(p)
            files.append(p)
    files.sort(key=lambda p: os.path.getmtime(p))
    return files


def _read_json_or_jsonl(path: str) -> list[dict]:
    """
    Read one file as JSON or JSONL and return a bounded list of records.

    This parser first attempts a full JSON parse to support the following
    patterns commonly seen in log outputs:

    * Single object: ``{"key": "value"}``
    * Wrapped items: ``{"items": [{...}, ...]}``
    * Top-level array: ``[{...}, {...}]``

    If the full parse fails, it falls back to line-delimited JSON (JSONL).
    Corrupted JSONL rows are skipped so that one bad line does not block the
    whole diagnosis.

    Security/reliability controls:

    * Skip overly large files (``MAX_FILE_SIZE``)
    * Limit parsed items per file (``MAX_ITEMS_PER_FILE``)
    """
    # ★ CPU/OOM対策: ファイルサイズチェック
    try:
        file_size = os.path.getsize(path)
        if file_size > MAX_FILE_SIZE:
            print(f"⚠️ {path} is too large ({file_size} bytes), skipping")
            return []
    except OSError:
        return []

    items: list[dict] = []

    def _bounded_extend(values: list) -> None:
        """Extend ``items`` up to ``MAX_ITEMS_PER_FILE`` entries."""
        remaining = MAX_ITEMS_PER_FILE - len(items)
        if remaining <= 0:
            return
        items.extend(values[:remaining])

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        if not content:
            return []

    # Prefer JSON first (handles leading whitespace safely).
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = None

    if data is not None:
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            _bounded_extend(data["items"])
        elif isinstance(data, list):
            _bounded_extend(data)
        else:
            _bounded_extend([data])
        return items

    # Fallback: JSONL mode
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            # 破損行は無視して続行
            continue
        # ★ CPU/OOM対策: アイテム数の上限チェック
        if len(items) >= MAX_ITEMS_PER_FILE:
            break
    return items


def _bump_kw(counter: dict, text: str):
    for w in KW_LIST:
        if w and (w in (text or "")):
            counter[w] = counter.get(w, 0) + 1


# ---- main analyzer -----------------------------------------------------
def analyze_logs():
    files = _iter_files()

    # TRUST_LOG_JSON がなくても、とりあえず警告だけでOK
    if not files and not os.path.exists(LOG_JSONL):
        print("⚠️ scripts/logs 内に解析対象のログが見つかりません。")
        return

    found_total  = len(files)
    parsed       = 0
    skipped_zero = 0
    skipped_bad  = 0

    # カテゴリ別メトリクス
    metrics = {
        "decide": {"count": 0},
        "health": {"count": 0},
        "status": {"count": 0},
        "other":  {"count": 0},
    }
    uncertainties: list[float] = []
    keywords: dict[str, int] = {}

    # ファイル群を走査
    for path in files:
        name = os.path.basename(path)
        if name.startswith("decide_"):
            cat = "decide"
        elif name.startswith("health_"):
            cat = "health"
        elif "status" in name:
            cat = "status"
        else:
            cat = "other"

        try:
            items = _read_json_or_jsonl(path)
        except Exception as e:
            skipped_bad += 1
            print(f"⚠️ {path} の解析中にエラー: {e}")
            continue

        if not items:
            skipped_zero += 1
            continue

        # スキーマ揺れを吸収して抽出
        for data in items:
            if not isinstance(data, dict):
                continue

            # query
            ctx   = data.get("context") or {}
            query = data.get("query") or ctx.get("query") or ""
            if query:
                _bump_kw(keywords, query)

            # 不確実性（あれば）
            chosen = (
                (data.get("response") or {}).get("chosen")
                or (data.get("result") or {}).get("chosen")
                or (data.get("decision") or {}).get("chosen")
                or data.get("chosen")
                or {}
            )
            unc = chosen.get("uncertainty", data.get("uncertainty", None))
            try:
                if unc is not None:
                    uncertainties.append(float(unc))
            except Exception:
                pass

        metrics[cat]["count"] += 1
        parsed += 1

    # ✨ TrustLog 健全性チェック（新機能）
    trustlog_stats = analyze_trustlog()

    # 📈 P2-2: 精度ベンチマークモニタリング
    accuracy_stats = analyze_accuracy_benchmarks()
    
    # 最終診断時刻（TrustLogから取得、なければ現在時刻）
    last_check = trustlog_stats.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    avg_unc = round(statistics.mean(uncertainties), 3) if uncertainties else 0.0

    result = {
        "total_files_found": found_total,
        "parsed_logs":       parsed,
        "skipped_zero":      skipped_zero,
        "skipped_badjson":   skipped_bad,
        "avg_uncertainty":   avg_unc,
        "keywords":          keywords,
        "last_check":        last_check,
        "by_category":       {k: v["count"] for k, v in metrics.items()},
        "trustlog":          trustlog_stats,  # ✨ TrustLog統計を追加
        "accuracy":          accuracy_stats,  # 📈 P2-2: 精度モニタリング
        "generated_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_dir":        str(LOG_DIR),
    }

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ---- console summary ------------------------------------------------
    print("\n== VERITAS Doctor Report (Enhanced) ==")
    print("✓ 検出(総):", found_total)
    print("✓ 解析OK :", parsed)
    print("↪ スキップ: 0B=", skipped_zero, ", JSON=", skipped_bad)
    print("🎯 平均不確実性:", avg_unc)
    print("🔑 キーワード出現頻度:", keywords)
    print("📅 最終診断時刻:", last_check)
    print("📊 カテゴリ内訳:", {k: v["count"] for k, v in metrics.items()})
    
    # ✨ TrustLog診断結果を表示
    print("\n🔒 TrustLog 診断:")
    print(f"   ステータス: {trustlog_stats['status']}")
    print(f"   総エントリ数: {trustlog_stats['entries']}")
    
    if trustlog_stats['status'] == 'not_found':
        print("   ⚠️ trust_log.jsonl が見つかりません")
    elif trustlog_stats['chain_valid']:
        print("   ✅ ハッシュチェーン検証: PASSED")
        if trustlog_stats['last_hash']:
            print(f"   🔑 最終ハッシュ: {trustlog_stats['last_hash']}")
    else:
        print("   ❌ ハッシュチェーン検証: FAILED")
        if trustlog_stats['chain_breaks'] > 0:
            print(f"   ⚠️ チェーン破損: {trustlog_stats['chain_breaks']} 箇所")
            if trustlog_stats['first_break']:
                fb = trustlog_stats['first_break']
                print(f"      最初の破損: Line {fb['line']} (ID: {fb['request_id']})")
        if trustlog_stats['hash_mismatches'] > 0:
            print(f"   ⚠️ ハッシュ不一致: {trustlog_stats['hash_mismatches']} 件")
            if trustlog_stats['first_mismatch']:
                fm = trustlog_stats['first_mismatch']
                print(f"      最初の不一致: Line {fm['line']} (ID: {fm['request_id']})")
    
    # 📈 P2-2: 精度モニタリングダッシュボード
    print("\n📈 精度モニタリング (P2-2 / Art. 15):")
    if accuracy_stats["status"] == "no_benchmark_dir":
        print("   ⚠️ ベンチマーク結果ディレクトリが見つかりません")
    elif accuracy_stats["status"] == "no_results":
        print("   ⚠️ ベンチマーク結果ファイルが見つかりません")
    else:
        print(f"   総実行数: {accuracy_stats['total_runs']}")
        print(f"   ファイル数: {accuracy_stats['benchmark_files']}")
        if accuracy_stats["accuracy_avg"] is not None:
            print(f"   精度 (平均): {accuracy_stats['accuracy_avg']:.4f}")
            print(f"   精度 (最小): {accuracy_stats['accuracy_min']:.4f}")
            print(f"   精度 (最大): {accuracy_stats['accuracy_max']:.4f}")
        if accuracy_stats["drift_detected"]:
            print(f"   ⚠️ ドリフト検出: {accuracy_stats['drift_details']}")
        else:
            print("   ✅ ドリフト: 検出なし")

    print("\n✅ 保存完了:", REPORT_PATH)


if __name__ == "__main__":
    analyze_logs()
