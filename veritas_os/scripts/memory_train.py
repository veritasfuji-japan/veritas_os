#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

# ▼ ここを修正：VERITAS_DIR を「このリポジトリ」にする
#   .../veritas_clean_test2/veritas_os/scripts/memory_train.py
#   という位置にある前提で、1つ上が repo root
REPO_ROOT = Path(__file__).resolve().parents[1]  # .../veritas_os
VERITAS_DIR = REPO_ROOT

# データセット置き場（リポジトリ内）
DATASET_DIR = VERITAS_DIR / "datasets"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIRS = [
    DATASET_DIR,
    VERITAS_DIR / "scripts" / "logs",  # 必要なら使う
]

# ▼ モデルの保存先もリポジトリ内 core/models に統一
MODEL_PATH = VERITAS_DIR / "core" / "models"
MODEL_PATH.mkdir(parents=True, exist_ok=True)
MODEL_ONNX_FILE = MODEL_PATH / "memory_model.onnx"
MODEL_METADATA_FILE = MODEL_PATH / "memory_model.metadata.json"


def _iter_dataset_files(data_dir: Path, patterns: list[str]) -> Iterable[Path]:
    """Yield dataset files in deterministic path order for stable training."""
    matched: list[Path] = []
    for pattern in patterns:
        matched.extend(data_dir.glob(pattern))

    for file_path in sorted(matched):
        if file_path.is_file():
            yield file_path


def _normalize_record(item: dict[str, object]) -> tuple[str, str] | None:
    """Normalize one raw dataset item into a `(text, label)` pair."""
    text = (
        item.get("input")
        or item.get("prompt")
        or item.get("text")
        or item.get("query")
    )
    label = item.get("decision") or item.get("label") or item.get("output")

    if not isinstance(text, str) or not isinstance(label, str):
        return None

    label_norm = label.strip().lower()
    if label_norm not in {"allow", "modify", "deny"}:
        return None

    return text.strip(), label_norm


def _iter_payloads(file_path: Path) -> Iterable[dict[str, object]]:
    """Yield dict payload records from a JSON or JSONL dataset file."""
    with file_path.open("r", encoding="utf-8") as handle:
        if file_path.suffix == ".jsonl":
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    yield payload
            return

        loaded = json.load(handle)
        if isinstance(loaded, list):
            for payload in loaded:
                if isinstance(payload, dict):
                    yield payload
            return

        if isinstance(loaded, dict):
            yield loaded


def load_decision_data() -> list[tuple[str, str]]:
    """Load labeled decision records from local JSON/JSONL files.

    This loader scans each directory configured in ``DATA_DIRS`` and parses
    ``*.json``/``*.jsonl`` files with multiple schema variants used by legacy
    benchmark outputs. Only records with ``allow``/``modify``/``deny`` labels
    are returned.
    """
    patterns = ["*.json", "*.jsonl"]
    records: list[tuple[str, str]] = []

    for data_dir in DATA_DIRS:
        if not data_dir.exists():
            continue

        for file_path in _iter_dataset_files(data_dir, patterns):
            try:
                for item in _iter_payloads(file_path):
                    record = _normalize_record(item)
                    if record is not None:
                        records.append(record)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"⚠️ skipped invalid dataset file: {file_path} ({exc})")
                continue

    print(f"[memory_train] loaded records: {len(records)}")
    return records


def train_memory_model(data: list[tuple[str, str]]) -> None:
    """Train MemoryOS classifier and export runtime-safe artifacts.

    Security warning:
        Runtime loading of pickle/joblib artifacts has been removed because it
        keeps a deserialization attack surface. This trainer therefore attempts
        ONNX export and always writes JSON metadata for auditability.
    """
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.utils.class_weight import compute_class_weight

    print(f"[DEBUG] train_memory_model: received {len(data)} records")
    print("[memory_train] enter: len(data) =", len(data))

    if not data:
        print("❌ No data to train.")
        return

    data = [(x, y) for (x, y) in data if y in ("allow", "modify", "deny")]
    print("[memory_train] after filter len(data) =", len(data))

    if not data:
        print("❌ No labeled data (allow/modify/deny).")
        return

    print("Class counts (filtered):", Counter(y for _, y in data))

    counts = Counter(y for _, y in data)
    min_ok = max(211, min(counts.values()))
    by_label = {"allow": [], "modify": [], "deny": []}
    for text, label in data:
        by_label[label].append((text, label))

    balanced = []
    for _, items in by_label.items():
        if not items:
            continue
        need = max(0, min_ok - len(items))
        balanced.extend(items)
        if need > 0:
            balanced.extend(random.choices(items, k=need))

    if not balanced:
        print("❌ Rebalance failed (no samples).")
        return

    print("Class counts (after rebalance):", Counter(y for _, y in balanced))

    x_texts, y = zip(*balanced)
    x_texts = [str(text) for text in x_texts]

    classes = np.array(["allow", "modify", "deny"])
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=list(y))
    class_weight = {label: weight for label, weight in zip(classes, weights)}
    print("[DEBUG] computed class_weight:", class_weight)

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2))
    x_matrix = vec.fit_transform(x_texts)

    clf = LogisticRegression(
        max_iter=400,
        class_weight=class_weight,
        n_jobs=None,
    )
    clf.fit(x_matrix, y)

    metadata = {
        "format": "onnx",
        "classes": list(classes),
        "ngram_range": [1, 2],
        "max_features": 4000,
        "records": len(balanced),
    }
    MODEL_METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        from skl2onnx import to_onnx
        from skl2onnx.common.data_types import StringTensorType
        from sklearn.pipeline import Pipeline

        pipeline = Pipeline(
            [
                ("vectorizer", vec),
                ("classifier", clf),
            ]
        )
        onnx_model = to_onnx(
            pipeline,
            initial_types=[("text", StringTensorType([None, 1]))],
            target_opset=17,
        )
        MODEL_ONNX_FILE.write_bytes(onnx_model.SerializeToString())
        print(f"✅ model saved → {MODEL_ONNX_FILE}")
    except Exception as exc:
        print(
            "⚠️ ONNX export skipped (install skl2onnx for runtime model): "
            f"{exc}"
        )
    print(f"✅ model metadata saved → {MODEL_METADATA_FILE}")


if __name__ == "__main__":
    data = load_decision_data()
    if data:
        train_memory_model(data)
