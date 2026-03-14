#!/usr/bin/env python3
"""Generate a safety-model calibration report from labeled decision records.

The report is intended to operationalize roadmap item #10 by producing
machine-readable and human-readable calibration evidence:
- Brier score
- Expected calibration error (ECE)
- Per-bucket confidence vs. empirical unsafe rate

Input format:
- JSONL file where each line is a JSON object.
- Predicted risk can be provided by one of:
  - ``predicted_risk``
  - ``risk``
  - ``fuji.risk``
- Ground truth unsafe label can be provided by one of:
  - ``actual_unsafe`` (bool/int/"true"/"false")
  - ``label`` ("unsafe"/"safe")

Security note:
- This tool does not perform PII masking; avoid feeding raw sensitive payloads.
  Use redacted datasets to reduce compliance risk.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class CalibrationBin:
    """One calibration bucket summary."""

    index: int
    sample_count: int
    avg_predicted_risk: float
    empirical_unsafe_rate: float
    absolute_gap: float


@dataclass(frozen=True)
class CalibrationReport:
    """Top-level calibration metrics for safety predictions."""

    generated_at: str
    source_path: str
    total_samples: int
    positive_rate: float
    brier_score: float
    expected_calibration_error: float
    bins: list[CalibrationBin]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate safety calibration report from labeled JSONL records.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to JSONL file with predicted risk and actual labels.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("audit") / "reports" / "safety_calibration_report.json",
        help="Output path for machine-readable JSON report.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("audit") / "reports" / "safety_calibration_report.md",
        help="Output path for Markdown summary report.",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=10,
        help="Number of equally spaced bins for ECE calculation.",
    )
    return parser.parse_args(argv)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if result < 0.0 or result > 1.0:
        return None
    return result


def _to_label(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "unsafe", "positive"}:
            return 1
        if lowered in {"0", "false", "safe", "negative"}:
            return 0
    return None


def _extract_predicted_risk(record: dict[str, Any]) -> float | None:
    direct = _safe_float(record.get("predicted_risk"))
    if direct is not None:
        return direct

    fallback = _safe_float(record.get("risk"))
    if fallback is not None:
        return fallback

    fuji = record.get("fuji")
    if isinstance(fuji, dict):
        return _safe_float(fuji.get("risk"))
    return None


def _extract_actual_label(record: dict[str, Any]) -> int | None:
    label = _to_label(record.get("actual_unsafe"))
    if label is not None:
        return label

    return _to_label(record.get("label"))


def _load_samples(path: Path) -> list[tuple[float, int]]:
    samples: list[tuple[float, int]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        risk = _extract_predicted_risk(payload)
        label = _extract_actual_label(payload)
        if risk is None or label is None:
            continue
        samples.append((risk, label))
    return samples


def _compute_brier_score(samples: list[tuple[float, int]]) -> float:
    if not samples:
        return 0.0
    return sum((pred - label) ** 2 for pred, label in samples) / len(samples)


def _compute_bins(samples: list[tuple[float, int]], n_bins: int) -> list[CalibrationBin]:
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for pred, label in samples:
        idx = min(int(pred * n_bins), n_bins - 1)
        buckets[idx].append((pred, label))

    results: list[CalibrationBin] = []
    for idx, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        avg_pred = sum(pred for pred, _ in bucket) / count
        emp_rate = sum(label for _, label in bucket) / count
        gap = abs(avg_pred - emp_rate)
        results.append(
            CalibrationBin(
                index=idx,
                sample_count=count,
                avg_predicted_risk=avg_pred,
                empirical_unsafe_rate=emp_rate,
                absolute_gap=gap,
            )
        )
    return results


def _compute_ece(bins: list[CalibrationBin], total_count: int) -> float:
    if total_count <= 0:
        return 0.0
    return sum((item.sample_count / total_count) * item.absolute_gap for item in bins)


def _build_report(samples: list[tuple[float, int]], source_path: Path, n_bins: int) -> CalibrationReport:
    total = len(samples)
    bins = _compute_bins(samples, n_bins=n_bins)
    positives = sum(label for _, label in samples)
    positive_rate = (positives / total) if total else 0.0
    return CalibrationReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_path=str(source_path),
        total_samples=total,
        positive_rate=positive_rate,
        brier_score=_compute_brier_score(samples),
        expected_calibration_error=_compute_ece(bins, total_count=total),
        bins=bins,
    )


def _write_json_report(report: CalibrationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown_report(report: CalibrationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Safety Calibration Report",
        "",
        f"- Generated at: `{report.generated_at}`",
        f"- Source: `{report.source_path}`",
        f"- Total samples: **{report.total_samples}**",
        f"- Positive (unsafe) rate: **{report.positive_rate:.3f}**",
        f"- Brier score: **{report.brier_score:.4f}**",
        (
            "- Expected calibration error (ECE): "
            f"**{report.expected_calibration_error:.4f}**"
        ),
        "",
        "## Bucket Details",
        "",
        "| Bin | Samples | Avg predicted risk | Empirical unsafe rate | Gap |",
        "|---:|---:|---:|---:|---:|",
    ]

    for item in report.bins:
        lines.append(
            "| "
            f"{item.index} | {item.sample_count} | {item.avg_predicted_risk:.3f} "
            f"| {item.empirical_unsafe_rate:.3f} | {item.absolute_gap:.3f} |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _validate_args(parsed: argparse.Namespace) -> None:
    if parsed.bins <= 1:
        raise ValueError("--bins must be greater than 1")


def main(argv: list[str] | None = None) -> int:
    parsed = _parse_args(argv or sys.argv[1:])

    try:
        _validate_args(parsed)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    input_path = parsed.input.resolve(strict=False)
    if not input_path.exists():
        print(f"ERROR: input file does not exist: {input_path}")
        return 2

    samples = _load_samples(input_path)
    if not samples:
        print(
            "SECURITY WARNING: no valid labeled samples were loaded. "
            "Calibration is not measurable; safety drift may go undetected."
        )
        return 1

    report = _build_report(samples, source_path=input_path, n_bins=parsed.bins)
    _write_json_report(report, parsed.output_json)
    _write_markdown_report(report, parsed.output_md)

    print(
        "Generated safety calibration report: "
        f"samples={report.total_samples}, "
        f"brier={report.brier_score:.4f}, "
        f"ece={report.expected_calibration_error:.4f}"
    )
    print(f"JSON: {parsed.output_json}")
    print(f"MD: {parsed.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
