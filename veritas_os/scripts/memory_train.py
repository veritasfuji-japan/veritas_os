#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import glob
import json
import random
from collections import Counter
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

print("[memory_train] running file:", __file__)

# ▼ ここを修正：VERITAS_DIR を「このリポジトリ」にする
#   .../veritas_clean_test2/veritas_os/scripts/memory_train.py
#   という位置にある前提で、1つ上が repo root
REPO_ROOT   = Path(__file__).resolve().parents[1]   # .../veritas_os
VERITAS_DIR = REPO_ROOT

# データセット置き場（リポジトリ内）
DATASET_DIR = VERITAS_DIR / "datasets"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIRS = [
    DATASET_DIR,
    VERITAS_DIR / "scripts" / "logs",   # 必要なら使う
]

# ▼ モデルの保存先もリポジトリ内 core/models に統一
MODEL_PATH = VERITAS_DIR / "core" / "models"
MODEL_PATH.mkdir(parents=True, exist_ok=True)


def load_decision_data() -> list[tuple[str, str]]:
    """Load labeled decision records from JSON/JSONL files.

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
            for file_path in glob.glob(str(data_dir / pattern)):
                try:
                    with open(file_path, "r", encoding="utf-8") as handle:
                        if file_path.endswith(".jsonl"):
                            payloads = [
                                json.loads(line)
                                for line in handle
                                if line.strip()
                            ]
                        else:
                            loaded = json.load(handle)
                            payloads = loaded if isinstance(loaded, list) else [loaded]
                except (OSError, json.JSONDecodeError) as exc:
                    print(f"⚠️ skipped invalid dataset file: {file_path} ({exc})")
                    continue

                for item in payloads:
                    if not isinstance(item, dict):
                        continue

                    text = (
                        item.get("input")
                        or item.get("prompt")
                        or item.get("text")
                        or item.get("query")
                    )
                    label = (
                        item.get("decision")
                        or item.get("label")
                        or item.get("output")
                    )
                    if isinstance(text, str) and isinstance(label, str):
                        label_norm = label.strip().lower()
                        if label_norm in {"allow", "modify", "deny"}:
                            records.append((text.strip(), label_norm))

    print(f"[memory_train] loaded records: {len(records)}")
    return records


def train_memory_model(data):
    from sklearn.utils.class_weight import compute_class_weight
    import numpy as np

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
    for x, y in data:
        by_label[y].append((x, y))

    balanced = []
    for lbl, items in by_label.items():
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

    X_texts, y = zip(*balanced)
    X_texts = [str(t) for t in X_texts]

    classes = np.array(["allow", "modify", "deny"])
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=list(y))
    class_weight = {c: w for c, w in zip(classes, weights)}
    print("[DEBUG] computed class_weight:", class_weight)

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2))
    X = vec.fit_transform(X_texts)

    clf = LogisticRegression(
        max_iter=400,
        class_weight=class_weight,
        n_jobs=None,
    )
    clf.fit(X, y)

    joblib.dump((vec, clf), MODEL_PATH / "memory_model.pkl")
    print(f"✅ model saved → {MODEL_PATH}/memory_model.pkl")


if __name__ == "__main__":
    data = load_decision_data()
    if data:
        train_memory_model(data)
