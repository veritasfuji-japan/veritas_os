#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os, json, glob, random
from pathlib import Path
from collections import Counter

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


# （load_decision_data 以下はそのままでOK）
# ...

if __name__ == "__main__":
    data = load_decision_data()
    if data:
        train_memory_model(data)
