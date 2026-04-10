# ============================================================
# Stage 1: builder — 依存ライブラリのインストールのみ
# テストファイル・docs・.git はここで除外され本番イメージに含まれない
# NOTE: requirements.txt installs the FULL dependency set.
#       For a slimmer image, copy pyproject.toml and run:
#       pip install --no-cache-dir --target /build/deps .
# ============================================================
FROM python:3.11.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY ./veritas_os/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target /build/deps -r /tmp/requirements.txt

# ============================================================
# Stage 2: runtime — ランタイムに必要なファイルのみをコピー
# ============================================================
FROM python:3.11.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/deps

WORKDIR /app

# セキュリティパッチ適用（ベースイメージの既知CVE修正）
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip setuptools wheel

# ビルドステージからインストール済みパッケージのみコピー（ビルドツール類を除外）
COPY --from=builder /build/deps /app/deps

# アプリケーションコードのみコピー（docs・tests・.git を除外）
COPY veritas_os/ ./veritas_os/
COPY packages/ ./packages/

# 非特権ユーザーで実行
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ★ M-4 修正: ヘルスチェック追加
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from http.client import HTTPConnection; c = HTTPConnection('localhost', 8000, timeout=3); c.request('GET', '/health'); exit(0 if c.getresponse().status == 200 else 1)" || exit 1

STOPSIGNAL SIGTERM
CMD ["uvicorn", "veritas_os.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
