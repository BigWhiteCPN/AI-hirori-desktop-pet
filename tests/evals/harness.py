"""Small dependency-free eval harness for persona regression tests."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EvalResult:
    suite: str
    name: str
    passed: bool
    elapsed_ms: float
    score: float = 1.0
    metrics: dict = field(default_factory=dict)
    error: str = ""


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def assert_contains(text, needle, message):
    if str(needle) not in str(text):
        raise AssertionError(message)


def run_case(suite, name, fn):
    started = time.perf_counter()
    try:
        metrics = fn() or {}
        score = float(metrics.pop("score", 1.0)) if isinstance(metrics, dict) else 1.0
        return EvalResult(
            suite=suite,
            name=name,
            passed=True,
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 1),
            score=round(score, 4),
            metrics=metrics if isinstance(metrics, dict) else {},
        )
    except Exception as exc:
        return EvalResult(
            suite=suite,
            name=name,
            passed=False,
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 1),
            score=0.0,
            error=str(exc),
        )


def summarize(results):
    total = len(results)
    passed = sum(1 for item in results if item.passed)
    avg_score = sum(item.score for item in results) / max(total, 1)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / max(total, 1), 4),
        "avg_score": round(avg_score, 4),
    }


def result_to_dict(result):
    return {
        "suite": result.suite,
        "name": result.name,
        "passed": result.passed,
        "elapsed_ms": result.elapsed_ms,
        "score": result.score,
        "metrics": result.metrics,
        "error": result.error,
    }


def write_reports(results, report_dir):
    os.makedirs(report_dir, exist_ok=True)
    summary = summarize(results)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "results": [result_to_dict(item) for item in results],
    }
    json_path = os.path.join(report_dir, "persona_eval_report.json")
    md_path = os.path.join(report_dir, "persona_eval_report.md")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# Persona Eval Report\n\n")
        handle.write(
            f"- total: {summary['total']}\n"
            f"- passed: {summary['passed']}\n"
            f"- failed: {summary['failed']}\n"
            f"- pass_rate: {summary['pass_rate']}\n"
            f"- avg_score: {summary['avg_score']}\n\n"
        )
        handle.write("| suite | case | status | score | elapsed_ms | error |\n")
        handle.write("| --- | --- | --- | ---: | ---: | --- |\n")
        for item in results:
            status = "PASS" if item.passed else "FAIL"
            error = str(item.error or "").replace("|", "\\|")
            handle.write(
                f"| {item.suite} | {item.name} | {status} | "
                f"{item.score:.4f} | {item.elapsed_ms:.1f} | {error} |\n"
            )
    return {"json": json_path, "markdown": md_path, **summary}
