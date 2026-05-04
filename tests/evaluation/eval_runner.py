"""
Evaluation runner for multi-agent quality measurement.

Usage:
  python -m tests.evaluation.eval_runner           # router-only comparison (fast)
  python -m tests.evaluation.eval_runner --llm     # full LLM end-to-end (slow, needs API key)
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from tests.evaluation.benchmark_queries import BENCHMARK_QUERIES, BenchmarkQuery
from core.router_rules import RouterRules, RouterStats


# ── Metric data classes ────────────────────────────────────────────

@dataclass
class EvalResult:
    query_id: str
    query_text: str
    category: str
    difficulty: str
    route_target: str | None = None
    route_rule: str = ""
    route_confidence: float = 0.0
    route_correct: bool = False
    latency_ms: float = 0.0
    agent_chain: list[str] = field(default_factory=list)
    handoff_count: int = 0
    llm_output: str = ""
    llm_error: str = ""
    scores: dict[str, float] = field(default_factory=dict)  # criterion → score (0-1)
    notes: str = ""


@dataclass
class EvalReport:
    total_queries: int = 0
    route_accuracy: float = 0.0
    category_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    results: list[EvalResult] = field(default_factory=list)
    summary: str = ""


# ── Router evaluation (fast, no LLM) ──────────────────────────────

def _route_category_ok(target: str | None, expected_category: str) -> bool:
    """Check if route target matches expected category."""
    if expected_category == "chat":
        return target == "chat"
    if expected_category == "code":
        return target in ("code", "executor")
    if expected_category == "review":
        return target in ("review", "executor")
    if expected_category == "research":
        return target in ("research", "executor")
    if expected_category == "multi":
        return target in ("code", "review", "research", "executor")
    return True


def evaluate_router() -> EvalReport:
    """Run router-only evaluation on all benchmark queries (fast)."""
    results = []
    RouterStats.reset()

    for query in BENCHMARK_QUERIES:
        t0 = time.perf_counter()
        route_result = RouterRules.match(query.text)
        latency_ms = (time.perf_counter() - t0) * 1000

        RouterStats.record(route_result, query.text)

        result = EvalResult(
            query_id=query.id,
            query_text=query.text,
            category=query.category,
            difficulty=query.difficulty,
            route_target=route_result.target,
            route_rule=route_result.matched_rule,
            route_confidence=route_result.confidence,
            route_correct=_route_category_ok(route_result.target, query.category),
            latency_ms=latency_ms,
        )
        results.append(result)

    # Compute aggregate metrics
    correct = sum(1 for r in results if r.route_correct)
    total = len(results)
    avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0

    # Category breakdown
    breakdown: dict[str, dict[str, Any]] = {}
    for cat in ("chat", "code", "review", "research", "multi"):
        cat_results = [r for r in results if r.category == cat]
        if not cat_results:
            continue
        cat_correct = sum(1 for r in cat_results if r.route_correct)
        breakdown[cat] = {
            "total": len(cat_results),
            "correct": cat_correct,
            "accuracy": f"{cat_correct / len(cat_results) * 100:.1f}%",
            "targets": sorted({r.route_target for r in cat_results if r.route_target is not None}),
        }

    report = EvalReport(
        total_queries=total,
        route_accuracy=correct / total if total > 0 else 0,
        category_breakdown=breakdown,
        avg_latency_ms=avg_latency,
        results=results,
        summary=f"Router: {correct}/{total} correct ({correct/total*100:.1f}%), "
                f"avg {avg_latency*1000:.1f}us/query"
        if total > 0 else "No queries evaluated",
    )
    return report


# ── LLM end-to-end evaluation (slow, needs real API) ──────────────

def evaluate_llm_pipeline(max_queries: int = 5) -> EvalReport | None:
    """Run full LLM pipeline evaluation on a subset of benchmark queries."""
    try:
        from core.openai_agentmain import OpenAIOrchestratedAgent
    except Exception as e:
        print(f"[Eval] Cannot import orchestrator: {e}")
        return None

    orchestrator = OpenAIOrchestratedAgent()
    if orchestrator.startup_error:
        print(f"[Eval] Orchestrator startup error: {orchestrator.startup_error}")
        return None

    results = []
    test_queries = BENCHMARK_QUERIES[:max_queries]

    for query in test_queries:
        print(f"\n[Eval] Running: {query.id} — {query.text[:60]}...")
        result = EvalResult(
            query_id=query.id,
            query_text=query.text,
            category=query.category,
            difficulty=query.difficulty,
        )

        t0 = time.perf_counter()
        try:
            import queue
            dq = queue.Queue()
            # Route first
            route_result = RouterRules.match(query.text)
            result.route_target = route_result.target
            result.route_rule = route_result.matched_rule
            result.route_confidence = route_result.confidence
            result.route_correct = _route_category_ok(route_result.target, query.category)

            # Submit task
            orchestrator.put_task(query.text, source="eval", output=dq)
            output_parts = []
            while True:
                item = dq.get(timeout=120)
                if "done" in item:
                    output_parts.append(str(item.get("done", "")))
                    break
                if "next" in item:
                    output_parts.append(str(item.get("next", "")))
            result.llm_output = "".join(output_parts)

        except queue.Empty:
            result.llm_error = "timeout (120s)"
        except Exception as e:
            result.llm_error = f"{type(e).__name__}: {e}"

        result.latency_ms = (time.perf_counter() - t0) * 1000
        results.append(result)

    avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0
    report = EvalReport(
        total_queries=len(results),
        avg_latency_ms=avg_latency,
        results=results,
        summary=f"LLM E2E: {len(results)} queries, avg {avg_latency/1000:.1f}s/query",
    )
    return report


# ── Report formatting ─────────────────────────────────────────────

def print_report(report: EvalReport) -> None:
    """Print a formatted evaluation report."""
    print("\n" + "=" * 60)
    print("  Multi-Agent Quality Evaluation Report")
    print("=" * 60)
    print(f"  Total queries: {report.total_queries}")
    print(f"  Route accuracy: {report.route_accuracy * 100:.1f}%")
    print(f"  Avg router latency: {report.avg_latency_ms * 1000:.1f}us")
    print()

    if report.category_breakdown:
        print("  Category Breakdown:")
        for cat, stats in sorted(report.category_breakdown.items()):
            print(f"    {cat:12s}: {stats['correct']}/{stats['total']} ({stats['accuracy']})")
        print()

    if report.results:
        print("  Per-Query Results:")
        for r in report.results:
            status = "OK" if r.route_correct else "WRONG"
            print(f"    [{status}] {r.query_id:10s} ({r.category:8s}) "
                  f"→ {r.route_target or 'none':10s} "
                  f"in {r.latency_ms*1000:.0f}us")
            if r.llm_output:
                preview = r.llm_output[:120].replace("\n", " ")
                print(f"           output: {preview}...")
            if r.llm_error:
                print(f"           ERROR: {r.llm_error}")
    print()

    # Save JSON report
    report_path = os.path.join(os.path.dirname(__file__), "eval_report.json")
    serializable = {
        "summary": report.summary,
        "total_queries": report.total_queries,
        "route_accuracy": report.route_accuracy,
        "avg_latency_ms": report.avg_latency_ms,
        "category_breakdown": report.category_breakdown,
        "results": [
            {
                "id": r.query_id,
                "category": r.category,
                "target": r.route_target,
                "rule": r.route_rule,
                "correct": r.route_correct,
                "latency_us": r.latency_ms * 1000,
                "error": r.llm_error,
            }
            for r in report.results
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"  Report saved to: {report_path}")


# ── CLI ────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-agent quality evaluation")
    parser.add_argument("--llm", action="store_true", help="Run full LLM end-to-end tests")
    parser.add_argument("--max-queries", type=int, default=3, help="Max LLM queries to run")
    args = parser.parse_args()

    print("Running router evaluation...")
    report = evaluate_router()
    print_report(report)

    if args.llm:
        print("\nRunning LLM end-to-end evaluation...")
        llm_report = evaluate_llm_pipeline(max_queries=args.max_queries)
        if llm_report:
            print_report(llm_report)


if __name__ == "__main__":
    main()
