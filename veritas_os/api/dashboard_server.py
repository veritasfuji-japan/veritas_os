from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pathlib import Path
import os
import json

app = FastAPI(title="VERITAS Dashboard")

# === パス設定 ===
# このファイル: .../veritas_clean_test2/veritas_os/api/dashboard_server.py
BASE_DIR = Path(__file__).resolve().parents[1]  # .../veritas_clean_test2/veritas_os

# 環境変数 VERITAS_LOG_DIR があればそちらを優先
default_log_dir = BASE_DIR / "scripts" / "logs"
LOG_DIR = Path(os.getenv("VERITAS_LOG_DIR", str(default_log_dir)))

LOG_DIR.mkdir(parents=True, exist_ok=True)

REPORT_HTML = LOG_DIR / "report.html"
STATUS_JSON = LOG_DIR / "drive_sync_status.json"

# === HTMLダッシュボード ===
# 置換: /dashboard をテンプレで返す
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    return HTMLResponse("""
<!doctype html><meta charset="utf-8">
<title>VERITAS Dashboard</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,monospace;background:#121212;color:#e0e0e0;padding:24px}
.card{border:1px solid #444;padding:12px;border-radius:8px;margin:8px 0;background:#111}
.badge{padding:2px 6px;border-radius:8px}
.badge.ok{background:#14532d;color:#d1fae5}
.badge.ng{background:#7f1d1d;color:#fee2e2}
</style>
<h1>VERITAS Dashboard</h1>
<div id="sync" class="card">Loading...</div>
<script>
async function load(){
  try{
    const r = await fetch('/api/status'); const s = await r.json();
    const ok = s.ok ? 'badge ok' : 'badge ng';
    document.getElementById('sync').innerHTML =
      `<b>Google Drive Sync</b> <span class="${ok}">${s.ok?'OK':'FAILED'}</span><br>
       Last Run (UTC): <code>${s.ended_at_utc||''}</code><br>
       Destination: <code>${s.dst||''}</code><br>
       Transferred files: <code>${s.transferred_files??0}</code>`;
  }catch(e){
    document.getElementById('sync').innerHTML='Status not found';
  }
}
load(); setInterval(load, 10000);
</script>
""")
# === Drive SyncステータスAPI ===
@app.get("/api/status", response_class=JSONResponse)
async def get_status():
    if STATUS_JSON.exists():
        try:
            data = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
            return data
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid JSON"}, status_code=500)
    else:
        return JSONResponse({"error": "status file not found"}, status_code=404)

# === HTMLレポートをダウンロード用に ===
@app.get("/download/report", response_class=FileResponse)
async def download_report():
    if REPORT_HTML.exists():
        return FileResponse(REPORT_HTML)
    return JSONResponse({"error": "not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
