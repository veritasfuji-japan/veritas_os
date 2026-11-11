# Disposable proof dependencies only; application checkout is bind-mounted RO.
# No live provider secrets or GitHub credentials belong in this image.
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git openssl ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY veritas_os/requirements.txt /opt/veritas/requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/veritas/requirements.txt \
    && python -m pip check

RUN git config --system --add safe.directory /workspace

ENV PYTHONPATH=/workspace \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /workspace
ENTRYPOINT ["python", "-m", "scripts.validation.reviewer_proof_runner_v1"]
