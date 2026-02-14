#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import glob
import json
import os
import random
from collections import Counter
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable

print("[memory_train] running file:", __file__)

REPO_ROOT = Path(__file__).resolve().parents[1]
VERITAS_DIR = REPO_ROOT

DATASET_DIR = VERITAS_DIR / "datasets"
DATASET_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIRS = [
    DATASET_DIR,
    VERITAS_DIR / "scripts" / "logs",
]

MODEL_PATH = VERITAS_DIR / "core" / "models"
MODEL_PATH.mkdir(parents=True, exist_ok=True)

VALID_LABELS = {"allow", "modify", "deny"}
TEXT_KEYS = ("text", "prompt", "input", "query", "message")
LABEL_KEYS = ("label", "decision", "verdict", "action")


def _extract_record(item: dict) -> tuple[str, str] | None:
    """Extract training text and label from a single JSON object.

    Args:
        item: One JSON object loaded from dataset files.

    Returns:
        A ``(text, label)`` tuple when required fields are found and the label is
        valid, otherwise ``None``.
    """
    label = next((str(item[k]).strip().lower() for k in LABEL_KEYS if k in item), None)
    if label not in VALID_LABELS:
        return None

    text = next((str(item[k]).strip() for k in TEXT_KEYS if k in item), "")
    if not text:
        return None

    return text, label


def _load_jsonl(path: Path) -> Iterable[tuple[str, str]]:
    """Load records from a JSON Lines dataset file.

    Invalid lines are skipped to keep the script resilient against partial logs.
    """
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARN] skip invalid JSONL: {path}:{line_no}")
                continue

            if isinstance(item, dict):
                record = _extract_record(item)
                if record:
                    yield record


def load_decision_data() -> list[tuple[str, str]]:
    """Load decision-training data from repository dataset directories.

    Supported formats are ``.json`` and ``.jsonl``. The function only accepts
    labels in ``allow/modify/deny`` and skips malformed entries.
    """
    patterns = ["*.json", "*.jsonl"]
    files: list[Path] = []

    for base in DATA_DIRS:
        if not base.exists():
            continue
        for pattern in patterns:
            matched = [Path(p) for p in glob.glob(os.path.join(base, pattern))]
            files.extend(matched)

    records: list[tuple[str, str]] = []
    for path in sorted(set(files)):
        if path.suffix == ".jsonl":
            records.extend(_load_jsonl(path))
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[WARN] skip invalid JSON: {path}")
            continue

        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            continue

        for item in payload:
            if isinstance(item, dict):
                record = _extract_record(item)
                if record:
                    records.append(record)

    print(f"[memory_train] loaded {len(records)} records from {len(files)} files")
    return records


def _load_training_dependencies() -> tuple[Any, Any, Any, Any, Any]:
    """Load optional ML dependencies only when model training is requested.

    Returns:
        Tuple containing ``numpy``, ``joblib``, ``TfidfVectorizer``,
        ``LogisticRegression`` and ``compute_class_weight``.

    Raises:
        RuntimeError: If one of the optional dependencies is not installed.
    """
    try:
        np = import_module("numpy")
        joblib = import_module("joblib")
        text_mod = import_module("sklearn.feature_extraction.text")
        linear_mod = import_module("sklearn.linear_model")
        weight_mod = import_module("sklearn.utils.class_weight")
    except ModuleNotFoundError as exc:
        missing_pkg = exc.name or "required dependency"
        raise RuntimeError(
            "memory_train requires optional training dependencies. "
            f"Missing package: {missing_pkg}."
        ) from exc

    return (
        np,
        joblib,
        text_mod.TfidfVectorizer,
        linear_mod.LogisticRegression,
        weight_mod.compute_class_weight,
    )


def train_memory_model(data):
    np, joblib, tfidf_vectorizer, logistic_regression, compute_class_weight = (
        _load_training_dependencies()
    )

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
    for items in by_label.values():
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
    x_texts = [str(t) for t in x_texts]

    classes = np.array(["allow", "modify", "deny"])
    weights = compute_class_weight(class_weight="balanced", classes=classes, y=list(y))
    class_weight = {c: w for c, w in zip(classes, weights)}
    print("[DEBUG] computed class_weight:", class_weight)

    vec = tfidf_vectorizer(max_features=4000, ngram_range=(1, 2))
    x_data = vec.fit_transform(x_texts)

    clf = logistic_regression(
        max_iter=400,
        class_weight=class_weight,
        n_jobs=None,
    )
    clf.fit(x_data, y)

    joblib.dump((vec, clf), MODEL_PATH / "memory_model.pkl")
    print(f"✅ model saved → {MODEL_PATH}/memory_model.pkl")


if __name__ == "__main__":
    data = load_decision_data()
    if data:
        train_memory_model(data)
