#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import glob
import json
import random
from collections import Counter
from pathlib import Path
from typing import Iterable

print("[memory_train] running file:", __file__)

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

        for pattern in patterns:
            for raw_path in glob.glob(str(data_dir / pattern)):
                file_path = Path(raw_path)
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
    """Train and persist the MemoryOS classifier from labeled records."""
    import joblib
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

    joblib.dump((vec, clf), MODEL_PATH / "memory_model.pkl")
    print(f"✅ model saved → {MODEL_PATH}/memory_model.pkl")


if __name__ == "__main__":
    data = load_decision_data()
    if data:
        train_memory_model(data)
