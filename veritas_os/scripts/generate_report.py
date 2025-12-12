#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VERITAS Doctor Dashboard Generator v2.5 (local .veritas layout)
- decide_*.json / decide_first_*.json を自動検出して集計
- ログ: veritas_os/scripts/logs
- MemoryOS / ValueEMA: 優先的に veritas_os/.veritas/ を参照し、
  なければ scripts/logs や project_root/data をフォールバック
"""

import json
import glob
import base64
import io
import statistics
import datetime
import collections
from pathlib import Path

# ---- Matplotlib はあれば使う（なければグラフなしでHTMLだけ出す）----
HAS_MPL = False
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    HAS_MPL = True

    # フォント設定（フォールバック付き）
    try:
        plt.rcParams.update({
            "font.family": "AppleGothic",
            "axes.unicode_minus": False,
        })
    except Exception:
        pass
except Exception:
    plt = None  # type: ignore

REPO_ROOT   = Path(__file__).resolve().parents[1]   # .../veritas_os
SCRIPTS_DIR = REPO_ROOT / "scripts"

# プロジェクトルート（.../veritas_clean_test2）
PROJECT_ROOT = REPO_ROOT.parent

# ログディレクトリは scripts/logs 固定
LOG_DIR = SCRIPTS_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

REPORT_HTML = LOG_DIR / "doctor_dashboard.html"
# doctor.py が doctor_report.json を書くので、ここでも同じ名前で上書きして OK
REPORT_JSON = LOG_DIR / "doctor_report.json"

# Value は .veritas/value_stats.json または project_root/data/value_stats.json を見る
DATA_DIR = PROJECT_ROOT / "data"
VERITAS_DIR = REPO_ROOT / ".veritas"

VALUE_CANDIDATES = [
    VERITAS_DIR / "value_stats.json",
    DATA_DIR / "value_stats.json",
]

MEMORY_CANDIDATES = [
    VERITAS_DIR / "memory.json",
    LOG_DIR / "memory.json",
]

# ---------- 共通関数 ----------
def b64_png_from_fig(fig):
    if not HAS_MPL:
        return None
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    if HAS_MPL:
        import matplotlib.pyplot as _plt  # type: ignore
        _plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")

def read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def iso_now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _as_list(v):
    """None/単体値/タプルも安全にリスト化"""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]

def _pick_existing(candidates):
    for p in candidates:
        if isinstance(p, Path) and p.exists():
            return p
    # どれも無ければ先頭をデフォルトとして返す
    return candidates[0]

# ---------- データ収集 ----------
def collect_decisions():
    records = []
    for pat in ["decide_*.json", "decide_first_*.json"]:
        for p in sorted(LOG_DIR.glob(pat)):
            j = read_json(p)
            if not isinstance(j, dict):
                continue

            # response / gate / fuji
            response = j.get("response", {})
            if not isinstance(response, dict):
                response = {}

            gate = response.get("gate", {})
            if not isinstance(gate, dict):
                gate = j.get("gate", {}) if isinstance(j.get("gate"), dict) else {}

            fuji: dict = {}
            resp_fuji = response.get("fuji")
            if isinstance(resp_fuji, dict) and resp_fuji:
                # response.fuji に中身があるとき優先
                fuji = resp_fuji
            else:
                top_fuji = j.get("fuji")
                if isinstance(top_fuji, dict):
                    fuji = top_fuji

            extras = j.get("extras") or response.get("extras") or {}
            if not isinstance(extras, dict):
                extras = {}
            metrics = extras.get("metrics") or {}
            if not isinstance(metrics, dict):
                metrics = {}

            # FUJI ステータス（生）と決定ステータス
            fuji_status = ""
            if isinstance(fuji, dict):
                fuji_status = (fuji.get("status") or "").lower()

            status = None
            if fuji_status in ("modify", "rejected", "allow"):
                # FUJI が明示されている場合はそれを優先
                status = "modify" if fuji_status == "modify" else fuji_status

            if not status and isinstance(gate, dict):
                status = (gate.get("decision_status") or "").lower()

            if not status and isinstance(response, dict):
                status = (response.get("decision_status") or "").lower()

            if not status:
                status = (j.get("decision_status") or "unknown").lower()

            # latency_ms を候補から総当たり（文字列も許容）
            latency_ms_raw = (
                metrics.get("latency_ms")
                or (j.get("meta") or {}).get("latency_ms")
                or j.get("latency_ms")
                or (response.get("meta") or {}).get("latency_ms")
                or (j.get("timing") or {}).get("latency_ms")
                or (j.get("timing") or {}).get("duration_ms")
                or j.get("duration_ms")
                or j.get("elapsed_ms")
            )
            latency_ms = None
            if latency_ms_raw is not None:
                try:
                    latency_ms = float(latency_ms_raw)
                except Exception:
                    latency_ms = None

            # memory evidence 件数
            mem_evi_count = None
            if isinstance(metrics.get("mem_evidence_count"), (int, float)):
                mem_evi_count = int(metrics["mem_evidence_count"])

            if mem_evi_count is None:
                evid = response.get("evidence") or j.get("evidence") or []
                mem_evi_count = 0
                if isinstance(evid, list):
                    for e in evid:
                        if not isinstance(e, dict):
                            continue
                        src = str(e.get("source", "") or "")
                        if src.startswith("internal:memory") or src.startswith("memory"):
                            mem_evi_count += 1

            # mtime
            try:
                mtime_str = datetime.datetime.fromtimestamp(
                    p.stat().st_mtime
                ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                mtime_str = ""

            # chosen title
            chosen_title = ""
            chosen_obj = j.get("chosen") or response.get("chosen")
            if isinstance(chosen_obj, dict):
                chosen_title = chosen_obj.get("title") or ""

            records.append({
                "file": str(p),
                "mtime": mtime_str,
                "status": status,
                "fuji_status": fuji_status or "unknown",
                "latency_ms": latency_ms,
                "mem_evidence": mem_evi_count,
                "risk": (gate.get("risk") if isinstance(gate, dict) else None),
                "redactions": _as_list(fuji.get("redactions") if isinstance(fuji, dict) else []),
                "mods": _as_list(fuji.get("modifications") if isinstance(fuji, dict) else []),
                "chosen": chosen_title,
            })
    return records

# ---------- MemoryOS 解析 ----------
def analyze_memory():
    total_memories = 0
    used_memories = 0
    citation_count = 0

    mem_path = _pick_existing(MEMORY_CANDIDATES)

    if not mem_path.exists():
        return {"total_memories": 0, "used_memories": 0, "citation_count": 0, "hit_rate": 0.0}

    data = read_json(mem_path)

    mem_list = []
    if isinstance(data, list):
        mem_list = data
    elif isinstance(data, dict) and isinstance(data.get("history"), list):
        mem_list = data["history"]

    for m in mem_list:
        if not isinstance(m, dict):
            continue

        v = m.get("value")
        if isinstance(v, dict):
            rec = v
        else:
            rec = m

        total_memories += 1

        if rec.get("used"):
            used_memories += 1

        citations = rec.get("citations") or []
        if isinstance(citations, list):
            citation_count += len(citations)

    hit_rate = (used_memories / total_memories * 100.0) if total_memories else 0.0
    return {
        "total_memories": total_memories,
        "used_memories": used_memories,
        "citation_count": citation_count,
        "hit_rate": round(hit_rate, 1),
    }

# ---------- Benchmarks 解析 ----------
def analyze_benchmarks():
    """
    scripts/logs/benchmarks/*.json を読み込み、
    bench_id ごとの簡易統計を返す。
    """
    bench_dir = LOG_DIR / "benchmarks"
    stats = {}

    if not bench_dir.exists():
        return stats

    files = sorted(bench_dir.glob("*.json"))
    if not files:
        return stats

    buckets = collections.defaultdict(list)

    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
        except Exception:
            continue

        if not isinstance(j, dict):
            continue

        bench_id = j.get("bench_id") or "unknown"
        name = j.get("name") or ""

        status_code = j.get("status_code")
        elapsed = j.get("elapsed_sec")
        resp = j.get("response_json") or {}

        telos = resp.get("telos_score")
        fuji = (resp.get("fuji") or {}).get("status")

        buckets[bench_id].append({
            "name": name,
            "status_code": status_code,
            "elapsed_sec": elapsed,
            "telos_score": telos,
            "fuji_status": fuji,
        })

    for bench_id, rows in buckets.items():
        name = rows[0].get("name") or ""

        status_codes = [r["status_code"] for r in rows if r.get("status_code") is not None]
        ok_count = sum(1 for s in status_codes if s == 200)

        elapsed_list = [r["elapsed_sec"] for r in rows if isinstance(r.get("elapsed_sec"), (int, float))]
        telos_list = [r["telos_score"] for r in rows if isinstance(r.get("telos_score"), (int, float))]
        fuji_list = [r["fuji_status"] for r in rows if r.get("fuji_status")]

        fuji_counter = collections.Counter(fuji_list)

        avg_elapsed = statistics.mean(elapsed_list) if elapsed_list else None
        avg_telos = statistics.mean(telos_list) if telos_list else None

        stats[bench_id] = {
            "name": name,
            "runs": len(rows),
            "ok_200": ok_count,
            "avg_elapsed_sec": round(avg_elapsed, 3) if avg_elapsed is not None else None,
            "avg_telos_score": round(avg_telos, 3) if avg_telos is not None else None,
            "fuji_counts": dict(fuji_counter),
        }

    return stats


# ---------- レポート生成 ----------
def build_report():
    decides = collect_decisions()
    total = len(decides)

    # FUJI のステータスを優先してカウント（なければ従来の status）
    counter_status = collections.Counter([
        (d.get("fuji_status") or d.get("status") or "unknown")
        for d in decides
    ])

    # Latency
    latencies = []
    for d in decides:
        v = d.get("latency_ms")
        if v is None:
            continue
        try:
            latencies.append(int(float(v)))
        except Exception:
            continue

    avg_latency = int(sum(latencies) / len(latencies)) if latencies else None
    p95_latency = (
        sorted(latencies)[int(0.95 * (len(latencies) - 1))]
        if latencies else None
    )

    # Memory evidence
    mem_counts = [int(d.get("mem_evidence", 0) or 0) for d in decides]
    avg_mem_evidence = round(sum(mem_counts) / len(mem_counts), 2) if mem_counts else 0.0

    # FUJI 分布
    fuji_counts = collections.Counter([d.get("fuji_status", "unknown") for d in decides])

    # redactions / mods
    red_items, mod_items = [], []
    for d in decides:
        red_items.extend([x for x in _as_list(d.get("redactions")) if x is not None])
        mod_items.extend([x for x in _as_list(d.get("mods")) if x is not None])
    red_terms = collections.Counter(red_items)
    mod_terms = collections.Counter(mod_items)

    # 日次決定数
    bucket = collections.Counter()
    for d in decides:
        m = d.get("mtime") or ""
        key = str(m)[:10] if isinstance(m, str) else ""
        if key:
            bucket[key] += 1
    days = sorted(bucket.keys())
    counts = [bucket[d] for d in days]

    # ---- グラフ生成（Matplotlib がある場合だけ）----
    img_decisions = None
    img_red = None
    img_mods = None
    img_latency = None
    img_mem = None
    img_fuji = None
    img_ema = None

    if HAS_MPL:
        if days:
            fig1 = plt.figure()
            plt.plot(range(len(days)), counts, marker="o")
            plt.title("決定数の推移（日次）")
            plt.xlabel("日付(インデックス)")
            plt.ylabel("件数")
            img_decisions = b64_png_from_fig(fig1)

        if red_terms:
            keys, vals = zip(*red_terms.most_common(10))
            fig2 = plt.figure()
            plt.bar(keys, vals)
            plt.title("Redaction 頻度 Top10")
            plt.xticks(rotation=15)
            img_red = b64_png_from_fig(fig2)

        if mod_terms:
            keys, vals = zip(*mod_terms.most_common(10))
            fig3 = plt.figure()
            plt.bar(keys, vals)
            plt.title("FUJI Modifications 頻度 Top10")
            plt.xticks(rotation=15)
            img_mods = b64_png_from_fig(fig3)

        if latencies:
            fig4 = plt.figure()
            plt.plot(range(len(latencies)), latencies, marker=".")
            plt.title("Latency 推移（ms）")
            plt.xlabel("ログ順（最新=右）")
            plt.ylabel("ms")
            img_latency = b64_png_from_fig(fig4)

        if mem_counts:
            fig5 = plt.figure()
            plt.plot(range(len(mem_counts)), mem_counts, marker="o")
            plt.title("Memory evidence 件数の推移")
            plt.xlabel("ログ順（最新=右）")
            plt.ylabel("件")
            img_mem = b64_png_from_fig(fig5)

        if fuji_counts:
            keys, vals = zip(*fuji_counts.items())
            fig6 = plt.figure()
            plt.bar(keys, vals)
            plt.title("FUJI 判定ステータス分布")
            plt.xticks(rotation=10)
            img_fuji = b64_png_from_fig(fig6)

        # Value EMA history
        try:
            hist = []
            val_path = _pick_existing(VALUE_CANDIDATES)

            if val_path.exists():
                with open(val_path, encoding="utf-8") as f:
                    vs = json.load(f)

                    if isinstance(vs, dict):
                        h = vs.get("history", [])
                        if isinstance(h, list):
                            hist = h
                    elif isinstance(vs, list):
                        hist = vs

            emas = []
            for item in hist:
                if not isinstance(item, dict):
                    continue
                try:
                    emas.append(float(item.get("ema", 0.5)))
                except Exception:
                    continue

            if emas:
                xs = list(range(len(emas)))
                fig_ema = plt.figure()
                plt.plot(xs, emas, marker="o")
                plt.title("Value EMA の推移")
                plt.xlabel("ログ順（最新=右）")
                plt.ylabel("EMA")
                img_ema = b64_png_from_fig(fig_ema)
        except Exception as e:
            print("[report] ema history skipped:", e)
            img_ema = None

    # 学習効果の可視化（meta_log / world.utility）
    meta_files = glob.glob(str(LOG_DIR / "meta_log*.jsonl"))
    decide_files = glob.glob(str(LOG_DIR / "decide_*.json"))

    reason_boosts = []
    world_utils = []

    for f in meta_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                for line in fp:
                    try:
                        j = json.loads(line)
                    except Exception:
                        continue
                    if "next_value_boost" in j:
                        try:
                            reason_boosts.append(float(j["next_value_boost"]))
                        except Exception:
                            continue
        except Exception:
            pass

    for f in decide_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                j = json.load(fp)
        except Exception:
            continue

        alts = []
        if isinstance(j.get("alternatives"), list):
            alts.extend(j["alternatives"])
        if isinstance(j.get("chosen"), dict):
            alts.append(j["chosen"])
        for a in alts:
            if not isinstance(a, dict):
                continue
            world = a.get("world", {}) or {}
            try:
                if "utility" in world:
                    world_utils.append(float(world["utility"]))
            except Exception:
                continue

    avg_reason_boost = round(statistics.mean(reason_boosts), 4) if reason_boosts else 0.0
    avg_world_utility = round(statistics.mean(world_utils), 4) if world_utils else 0.0

    # value_ema (最新値)
    value_ema = 0.5
    try:
        val_path = _pick_existing(VALUE_CANDIDATES)
        if val_path.exists():
            with open(val_path, encoding="utf-8") as f:
                vs = json.load(f)

                if isinstance(vs, dict):
                    value_ema = float(vs.get("ema", 0.5))
                elif isinstance(vs, list) and vs:
                    last = vs[-1]
                    if isinstance(last, dict):
                        value_ema = float(last.get("ema", 0.5))
    except Exception as e:
        print("[report] value_ema load skipped:", e)
        value_ema = 0.5

    mem_stats = analyze_memory()
    bench_stats = analyze_benchmarks()

    report = {
        "generated_at": iso_now(),
        "total_decisions": total,
        "status_counts": dict(counter_status),
        "redactions": dict(red_terms),
        "modifications": dict(mod_terms),
        "value_ema": round(value_ema, 4),
        "source_folder": str(LOG_DIR),
        "memory": mem_stats,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "avg_memory_evidence": avg_mem_evidence,
        "fuji_status_counts": dict(fuji_counts),
        "avg_reason_boost": avg_reason_boost,
        "avg_world_utility": avg_world_utility,
        "benchmarks": bench_stats,
        "has_matplotlib": HAS_MPL,
    }

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    ema_block = (
        f"<img src='data:image/png;base64,{img_ema}'/>"
        if img_ema
        else ("<i>Matplotlib が無効のためグラフなし</i>" if not HAS_MPL else "<i>データなし</i>")
    )
    status_str = json.dumps(report["status_counts"], ensure_ascii=False)

    # Benchmarks セクション用 HTML
    if bench_stats:
        bench_rows_html = ""
        for bid, st in bench_stats.items():
            name = st.get("name") or ""
            runs = st.get("runs")
            ok_200 = st.get("ok_200")
            avg_el = st.get("avg_elapsed_sec")
            avg_tel = st.get("avg_telos_score")
            fuji_counts_row = st.get("fuji_counts") or {}

            bench_rows_html += f"""
      <tr>
        <td><code>{bid}</code></td>
        <td>{name}</td>
        <td style="text-align:right">{runs}</td>
        <td style="text-align:right">{ok_200}</td>
        <td style="text-align:right">{avg_el if avg_el is not None else 'N/A'}</td>
        <td style="text-align:right">{avg_tel if avg_tel is not None else 'N/A'}</td>
        <td><code>{json.dumps(fuji_counts_row, ensure_ascii=False)}</code></td>
      </tr>
"""
    else:
        bench_rows_html = "<tr><td colspan='7'><i>ベンチマーク結果なし</i></td></tr>"

    def img_or_placeholder(img_b64):
        if img_b64:
            return f"<img src='data:image/png;base64,{img_b64}'/>"
        return "<i>Matplotlib が無効のためグラフなし</i>" if not HAS_MPL else "<i>データなし</i>"

    html = f"""<!doctype html>
<html lang="ja"><meta charset="utf-8">
<title>VERITAS Doctor Dashboard</title>
<body style="background:#0f1117;color:#e6edf3;font-family:-apple-system,system-ui,Segoe UI,Roboto;">
<h1>🩺 VERITAS Doctor Dashboard</h1>
<p>生成日時: {report['generated_at']}</p>
<p>データ元フォルダ: <code>{report['source_folder']}</code></p>
<p>Matplotlib: {"ON" if HAS_MPL else "OFF (グラフはテキストのみ)"}</p>

<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  <h3>サマリー</h3>
  <table>
    <tr><td>決定総数</td><td>{total}</td></tr>
    <tr><td>Status分布</td><td><code>{status_str}</code></td></tr>
    <tr><td>価値EMA(total)</td><td>{report.get('value_ema','N/A')}</td></tr>
    <tr><td>平均応答時間</td><td>{report.get('avg_latency_ms','N/A')} ms（p95: {report.get('p95_latency_ms','N/A')} ms）</td></tr>
    <tr><td>Memory evidence平均</td><td>{report.get('avg_memory_evidence','N/A')} 件</td></tr>
    <tr><td>平均 Value Boost</td><td>{report.get('avg_reason_boost','N/A')}</td></tr>
    <tr><td>平均 world.utility</td><td>{report.get('avg_world_utility','N/A')}</td></tr>
  </table>
</div>

<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px;margin-top:12px">
  <h3>MemoryOS 指標</h3>
  <table>
    <tr><td>総メモリ件数</td><td>{mem_stats['total_memories']}</td></tr>
    <tr><td>活用（used=True）</td><td>{mem_stats['used_memories']}</td></tr>
    <tr><td>引用総数</td><td>{mem_stats['citation_count']}</td></tr>
    <tr><td>記憶ヒット率</td><td>{mem_stats['hit_rate']}%</td></tr>
  </table>
</div>

<h3>決定数の推移</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {img_or_placeholder(img_decisions)}
</div>

<h3>Redaction 頻度</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {img_or_placeholder(img_red)}
</div>

<h3>Latency 推移（ms）</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {img_or_placeholder(img_latency)}
</div>

<h3>Memory evidence 件数の推移</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {img_or_placeholder(img_mem)}
</div>

<h3>FUJI 判定ステータス分布</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {img_or_placeholder(img_fuji)}
</div>

<h3>Value EMA の推移</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  {ema_block}
</div>

<h3>Benchmarks 概要</h3>
<div style="background:#161b22;padding:16px;border-radius:8px;max-width:900px">
  <table border="0" cellspacing="4" cellpadding="4">
    <thead>
      <tr>
        <th>bench_id</th>
        <th>name</th>
        <th>runs</th>
        <th>200 OK</th>
        <th>avg elapsed (sec)</th>
        <th>avg telos_score</th>
        <th>FUJI 分布</th>
      </tr>
    </thead>
    <tbody>
      {bench_rows_html}
    </tbody>
  </table>
</div>

</body></html>
"""
    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("✅ Doctor Dashboard 生成完了：", REPORT_HTML)
    print("🗂 JSON Summary:", REPORT_JSON)

if __name__ == "__main__":
    build_report()

