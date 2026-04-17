#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Financial PoC runner for deterministic expected-semantics validation.

This runner executes a compact financial PoC question pack against `/v1/decide`
and compares runtime response semantics to fixture `expected_semantics`.

Design goals:
- reproducible and lightweight (no benchmark infra dependencies),
- machine-readable mismatch diffs,
- quantified pass/fail/warning summary for demo and benchmark handoff.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

import requests

from veritas_os.core.decision_semantics import canonicalize_gate_decision

DEFAULT_FIXTURE_PATH = Path("veritas_os/sample_data/governance/financial_poc_questions.json")
DEFAULT_API_URL = "http://localhost:8000/v1/decide"
DEFAULT_TIMEOUT_SECONDS = 15.0

_NEXT_ACTION_ALIASES = {
    "NEEDS_HUMAN_REVIEW": "PREPARE_HUMAN_REVIEW_PACKET",
    "REJECT_REQUEST": "DO_NOT_EXECUTE",
}


@dataclass(frozen=True)
class PocQuestion:
    """One financial PoC question with expected semantics."""

    question_id: str
    category: str
    question: str
    expected_semantics: dict[str, Any]
    template_id: str | None = None


@dataclass(frozen=True)
class CaseResult:
    """Evaluation outcome for one PoC question."""

    question_id: str
    status: str
    mismatch_count: int
    mismatches: dict[str, dict[str, Any]]
    template_id: str | None
    request_id: str | None
    error: str | None


def _normalize_next_action(value: Any) -> str:
    """Normalize next_action labels into stable canonical labels."""
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    return _NEXT_ACTION_ALIASES.get(normalized, normalized)


def compare_expected_semantics(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return field-level mismatch diff between expected and actual semantics."""
    mismatches: dict[str, dict[str, Any]] = {}

    expected_gate = canonicalize_gate_decision(expected.get("gate_decision"))
    actual_gate = canonicalize_gate_decision(actual.get("gate_decision"))
    if expected_gate != actual_gate:
        mismatches["gate_decision"] = {"expected": expected_gate, "actual": actual_gate}

    expected_business = expected.get("business_decision")
    actual_business = actual.get("business_decision")
    if expected_business != actual_business:
        mismatches["business_decision"] = {
            "expected": expected_business,
            "actual": actual_business,
        }

    expected_action = _normalize_next_action(expected.get("next_action"))
    actual_action = _normalize_next_action(actual.get("next_action"))
    if expected_action != actual_action:
        mismatches["next_action"] = {"expected": expected_action, "actual": actual_action}

    expected_evidence = expected.get("required_evidence")
    actual_evidence = actual.get("required_evidence")
    if expected_evidence != actual_evidence:
        mismatches["required_evidence"] = {
            "expected": expected_evidence,
            "actual": actual_evidence,
        }

    expected_human = bool(expected.get("human_review_required"))
    actual_human = bool(actual.get("human_review_required"))
    if expected_human != actual_human:
        mismatches["human_review_required"] = {
            "expected": expected_human,
            "actual": actual_human,
        }

    return mismatches


def load_questions(path: Path) -> list[PocQuestion]:
    """Load PoC questions from fixture JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions: list[PocQuestion] = []
    for item in payload:
        questions.append(
            PocQuestion(
                question_id=str(item.get("question_id", "")).strip(),
                category=str(item.get("category", "")).strip(),
                question=str(item.get("question", "")).strip(),
                expected_semantics=dict(item.get("expected_semantics") or {}),
                template_id=(
                    str(item["template_id"]).strip() if item.get("template_id") is not None else None
                ),
            )
        )
    return questions


def _build_request_payload(question: PocQuestion) -> dict[str, Any]:
    """Build `/v1/decide` request payload for one PoC question."""
    context: dict[str, Any] = {
        "user_id": "financial_poc_runner",
        "category": question.category,
        "source": "financial_poc_pack",
    }
    if question.template_id:
        context["template_id"] = question.template_id

    return {
        "query": question.question,
        "context": context,
    }


def _call_decide_api(
    *,
    api_url: str,
    api_key: str,
    timeout_seconds: float,
    question: PocQuestion,
) -> dict[str, Any]:
    """Call `/v1/decide` and return parsed JSON payload."""
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }
    response = requests.post(
        api_url,
        headers=headers,
        json=_build_request_payload(question),
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _dry_run_response(question: PocQuestion) -> dict[str, Any]:
    """Return deterministic synthetic response for dry-run validation."""
    expected = question.expected_semantics
    return {
        "request_id": f"dry-run-{question.question_id}",
        "gate_decision": expected.get("gate_decision"),
        "business_decision": expected.get("business_decision"),
        "next_action": expected.get("next_action"),
        "required_evidence": expected.get("required_evidence"),
        "human_review_required": expected.get("human_review_required"),
    }


def _evaluate_questions(
    questions: list[PocQuestion],
    fetcher: Callable[[PocQuestion], dict[str, Any]],
) -> list[CaseResult]:
    """Evaluate all PoC questions with provided response fetcher."""
    results: list[CaseResult] = []
    for question in questions:
        try:
            payload = fetcher(question)
        except Exception as exc:  # pragma: no cover - guarded in tests via warning path
            results.append(
                CaseResult(
                    question_id=question.question_id,
                    status="warning",
                    mismatch_count=0,
                    mismatches={},
                    template_id=question.template_id,
                    request_id=None,
                    error=str(exc),
                )
            )
            continue

        mismatches = compare_expected_semantics(question.expected_semantics, payload)
        status = "pass" if not mismatches else "fail"
        results.append(
            CaseResult(
                question_id=question.question_id,
                status=status,
                mismatch_count=len(mismatches),
                mismatches=mismatches,
                template_id=question.template_id,
                request_id=str(payload.get("request_id", "")).strip() or None,
                error=None,
            )
        )
    return results


def _summarize(results: list[CaseResult]) -> dict[str, Any]:
    """Build quantitative summary from case results."""
    counts = {
        "pass": sum(result.status == "pass" for result in results),
        "fail": sum(result.status == "fail" for result in results),
        "warning": sum(result.status == "warning" for result in results),
    }
    total = len(results)
    evaluated = total - counts["warning"]
    pass_rate = (counts["pass"] / evaluated) if evaluated > 0 else 0.0

    return {
        "total": total,
        "counts": counts,
        "pass_rate": round(pass_rate, 4),
        "success_criteria": {
            "minimum_pass_rate": 0.9,
            "no_failures_required_for_demo": True,
            "allow_warnings_for_connectivity_only": True,
        },
    }


def run_financial_poc(
    *,
    input_path: Path,
    dry_run: bool,
    api_url: str,
    api_key: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Run financial PoC pack and return machine-readable report."""
    questions = load_questions(input_path)
    if dry_run:
        results = _evaluate_questions(questions, fetcher=_dry_run_response)
    else:
        results = _evaluate_questions(
            questions,
            fetcher=lambda question: _call_decide_api(
                api_url=api_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                question=question,
            ),
        )

    summary = _summarize(results)
    return {
        "meta": {
            "mode": "dry-run" if dry_run else "live",
            "input_path": str(input_path),
            "api_url": api_url,
        },
        "summary": summary,
        "cases": [
            {
                "question_id": result.question_id,
                "template_id": result.template_id,
                "status": result.status,
                "mismatch_count": result.mismatch_count,
                "mismatches": result.mismatches,
                "request_id": result.request_id,
                "error": result.error,
            }
            for result in results
        ],
    }


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments for financial PoC runner."""
    parser = argparse.ArgumentParser(
        description="Run financial PoC questions and compare expected semantics."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_FIXTURE_PATH),
        help="Path to PoC question JSON fixture.",
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("VERITAS_API_URL", DEFAULT_API_URL),
        help="Target /v1/decide endpoint URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("VERITAS_API_KEY", ""),
        help="API key for /v1/decide calls (not required for --dry-run).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout seconds for each /v1/decide call.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output report path in JSON format.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip API calls and validate fixture plumbing with synthetic responses.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entry point for financial PoC runner."""
    args = _parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"[financial-poc] input file not found: {input_path}")

    if not args.dry_run and not str(args.api_key).strip():
        raise SystemExit(
            "[financial-poc] --api-key (or VERITAS_API_KEY) is required for live mode"
        )

    if not args.dry_run and str(args.api_url).startswith("http://"):
        print(
            "[financial-poc][security-warning] Using HTTP endpoint. "
            "Use HTTPS for any non-local environment."
        )

    report = run_financial_poc(
        input_path=input_path,
        dry_run=bool(args.dry_run),
        api_url=str(args.api_url),
        api_key=str(args.api_key),
        timeout_seconds=float(args.timeout),
    )

    summary = report["summary"]
    counts = summary["counts"]
    print(
        "[financial-poc] "
        f"total={summary['total']} pass={counts['pass']} fail={counts['fail']} "
        f"warning={counts['warning']} pass_rate={summary['pass_rate']:.4f}"
    )

    for case in report["cases"]:
        print(
            " - "
            f"{case['question_id']}: status={case['status']} "
            f"mismatch_count={case['mismatch_count']}"
        )

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[financial-poc] report saved: {output_path}")


if __name__ == "__main__":
    main()
