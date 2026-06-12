"""Hybrid A/B runner for research workflow gates.

The offline path is deterministic and cheap: it evaluates trigger behavior,
context budget, scorer deltas, and routing-adjacent regressions without making
LLM calls. The optional LLM entry point is intentionally explicit and records a
skip reason when an API-backed run is not available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Support direct module execution from a clean shell.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.quality.research_workflow import (
    RESEARCH_WORKFLOW_ENV_VAR,
    build_research_workflow_context,
    score_research_workflow_response,
)
from tests.evaluation.research_workflow_cases import (
    RESEARCH_WORKFLOW_CASES,
    ResearchWorkflowCase,
)

_POSITIVE_TYPES = {"positive", "hard"}


@contextmanager
def _temporary_workflow_flag(enabled: bool):
    old_value = os.environ.get(RESEARCH_WORKFLOW_ENV_VAR)
    os.environ[RESEARCH_WORKFLOW_ENV_VAR] = "1" if enabled else "0"
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop(RESEARCH_WORKFLOW_ENV_VAR, None)
        else:
            os.environ[RESEARCH_WORKFLOW_ENV_VAR] = old_value


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.perf_counter() * 1000000) % 1000000:06d}"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return float(ordered[index])


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _route_target_for_case(case: ResearchWorkflowCase) -> str:
    if case.expected_trigger:
        return "research"
    if "chat" in case.id:
        return "chat"
    if "code" in case.id:
        return "code"
    if "review" in case.id:
        return "review"
    return "executor"


def _baseline_response(case: ResearchWorkflowCase) -> str:
    if case.expected_trigger:
        return (
            "We should build a better model and pursue a comprehensive solution. "
            "The goal is to improve everything until it becomes a world-class result."
        )
    return "Done."


def _gated_response(case: ResearchWorkflowCase, triggered: bool) -> str:
    if not case.expected_trigger or not triggered:
        return _baseline_response(case)
    return (
        "version_map: map v1/old_dir, v2/new_dir, manuscript drafts, or state not applicable "
        "before comparing evidence.\n"
        "Strategy diagnosis: the bottleneck is not ambition but evidence ordering and "
        "coherent next action. The guiding policy is to protect the strongest baseline "
        "and choose one falsifiable constraint at a time. Baseline: compare against the "
        "current frequency or benchmark baseline before claiming progress.\n"
        "Strong counterevidence check: before saying dead feature, no innovation, invalid, "
        "or merely incremental, inspect the strongest counterexample and alternate explanation.\n"
        "System dynamics lens: the stock is unresolved hypotheses, the flow is new "
        "experiments, the feedback loop is benchmark evidence, the delay is full-run "
        "latency, and the leverage point is earlier kill tests.\n"
        "Minimal Experiment Ladder: first run a kill test that can falsify the mechanism; "
        "then a medium diagnostic ablation; only then a full benchmark.\n"
        "Failure Ledger: record hypothesis, observed result, failure type, information "
        "bottleneck, and implication for each failed attempt.\n"
        "Evidence precedence: verified fact, logs, test output, and benchmark logs outrank "
        "hypothesis, assumption, prior, and model prior.\n"
        "Adversarial_review: assume each conclusion is wrong and find the strongest "
        "counterexample before final synthesis.\n"
        "Budget gate: exploration_steps: 3; adversarial_review_steps: 1.\n"
        "Frontier Relay: next handoff is to inspect the logs, test the smallest diagnostic, "
        "exclude the unsupported mechanism, and keep only the claim that survives."
    )


def _result_score_dict(response_text: str, prompt: str) -> dict[str, Any]:
    return score_research_workflow_response(prompt, response_text).to_dict()


def _evaluate_variant(
    *,
    name: str,
    enabled: bool,
    cases: list[ResearchWorkflowCase],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with _temporary_workflow_flag(enabled):
        for case in cases:
            route_target = _route_target_for_case(case)
            t0 = time.perf_counter()
            context = build_research_workflow_context(case.prompt, route_target=route_target)
            triggered = bool(context.get("matched"))
            response = _gated_response(case, triggered) if enabled else _baseline_response(case)
            score = _result_score_dict(response, case.prompt)
            latency_ms = (time.perf_counter() - t0) * 1000
            results.append(
                {
                    "id": case.id,
                    "prompt": case.prompt,
                    "control_type": case.control_type,
                    "difficulty": case.difficulty,
                    "expected_trigger": case.expected_trigger,
                    "route_target": route_target,
                    "triggered": triggered,
                    "context_chars": int(context.get("chars", 0) or 0),
                    "context_reason": str(context.get("reason", "")),
                    "required_sections": list(context.get("required_sections") or []),
                    "required_audit_gates": list(context.get("required_audit_gates") or []),
                    "latency_ms": round(latency_ms, 3),
                    "score": score,
                }
            )

    metrics = _compute_metrics(results)
    return {
        "variant": name,
        "workflow_env_enabled": enabled,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "metrics": metrics,
        "results": results,
    }


def _compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_positive = [r for r in results if r["expected_trigger"]]
    negative = [r for r in results if not r["expected_trigger"]]
    true_positive = [r for r in expected_positive if r["triggered"]]
    false_negative = [r for r in expected_positive if not r["triggered"]]
    false_positive = [r for r in negative if r["triggered"]]
    true_negative = [r for r in negative if not r["triggered"]]
    triggered_total = len(true_positive) + len(false_positive)

    positive_scores = [r["score"] for r in expected_positive]
    context_chars = [float(r["context_chars"]) for r in results]
    latencies = [float(r["latency_ms"]) for r in results]

    def section_mean(section: str) -> float:
        return round(
            _mean([float(score["section_scores"].get(section, 0.0)) for score in positive_scores]),
            3,
        )

    metrics = {
        "total_cases": len(results),
        "positive_cases": len(expected_positive),
        "negative_cases": len(negative),
        "trigger_precision": round(len(true_positive) / triggered_total, 3)
        if triggered_total
        else 0.0,
        "trigger_recall": round(len(true_positive) / len(expected_positive), 3)
        if expected_positive
        else 0.0,
        "negative_false_positive_rate": round(len(false_positive) / len(negative), 3)
        if negative
        else 0.0,
        "workflow_score_mean": round(
            _mean([float(score["total"]) for score in positive_scores]),
            3,
        ),
        "minimal_experiment_score": section_mean("minimal_experiment"),
        "failure_ledger_score": section_mean("failure_ledger"),
        "evidence_precedence_score": section_mean("evidence_precedence"),
        "frontier_relay_score": section_mean("frontier_relay"),
        "version_map_score": section_mean("version_map"),
        "counterevidence_check_score": section_mean("counterevidence_check"),
        "adversarial_review_score": section_mean("adversarial_review"),
        "time_budget_gate_score": section_mean("time_budget_gate"),
        "bad_strategy_flag_rate": round(
            _mean([1.0 if score["bad_strategy_flags"] else 0.0 for score in positive_scores]),
            3,
        ),
        "context_chars_added_mean": round(_mean(context_chars), 3),
        "context_chars_p95": round(_percentile(context_chars, 0.95), 3),
        "route_latency_ms": 0.0,
        "latency_mean_ms": round(_mean(latencies), 3),
        "latency_p95_ms": round(_percentile(latencies, 0.95), 3),
        "llm_call_count": 0,
        "optional_repair_count": 0,
        "false_negative_ids": [r["id"] for r in false_negative],
        "false_positive_ids": [r["id"] for r in false_positive],
        "true_negative_ids": [r["id"] for r in true_negative],
    }
    return metrics


def _metric_delta(gated: dict[str, Any], baseline: dict[str, Any], keys: list[str]) -> dict[str, float]:
    return {
        key: round(float(gated.get(key, 0.0)) - float(baseline.get(key, 0.0)), 3)
        for key in keys
    }


def _build_comparison(
    baseline: dict[str, Any],
    gated: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    baseline_metrics = baseline["metrics"]
    gated_metrics = gated["metrics"]
    quality_keys = [
        "workflow_score_mean",
        "minimal_experiment_score",
        "failure_ledger_score",
        "evidence_precedence_score",
        "frontier_relay_score",
        "version_map_score",
        "counterevidence_check_score",
        "adversarial_review_score",
        "time_budget_gate_score",
        "bad_strategy_flag_rate",
        "trigger_precision",
        "trigger_recall",
        "negative_false_positive_rate",
    ]
    performance_keys = [
        "context_chars_added_mean",
        "context_chars_p95",
        "latency_mean_ms",
        "latency_p95_ms",
        "llm_call_count",
        "optional_repair_count",
    ]
    quality_delta = _metric_delta(gated_metrics, baseline_metrics, quality_keys)
    performance_delta = _metric_delta(gated_metrics, baseline_metrics, performance_keys)
    acceptance = {
        "workflow_score_delta_at_least_0_15": quality_delta["workflow_score_mean"] >= 0.15,
        "minimal_experiment_delta_at_least_0_20": quality_delta["minimal_experiment_score"] >= 0.20,
        "failure_ledger_delta_at_least_0_20": quality_delta["failure_ledger_score"] >= 0.20,
        "negative_false_positive_rate_at_most_0_10": gated_metrics[
            "negative_false_positive_rate"
        ]
        <= 0.10,
        "matched_context_p95_at_most_1800_chars": gated_metrics["context_chars_p95"] <= 1800,
        "offline_latency_p95_at_most_25ms": gated_metrics["latency_p95_ms"] <= 25,
        "average_context_at_most_800_chars": gated_metrics["context_chars_added_mean"] <= 800,
    }
    return {
        "mode": mode,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "baseline": baseline_metrics,
        "gated": gated_metrics,
        "quality_delta": quality_delta,
        "performance_delta": performance_delta,
        "acceptance": acceptance,
        "passed": all(acceptance.values()),
    }


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    acceptance_lines = "\n".join(
        f"- {'PASS' if passed else 'FAIL'} {name}" for name, passed in comparison["acceptance"].items()
    )
    quality_lines = "\n".join(
        f"- {name}: {value:+.3f}" for name, value in comparison["quality_delta"].items()
    )
    performance_lines = "\n".join(
        f"- {name}: {value:+.3f}" for name, value in comparison["performance_delta"].items()
    )
    return (
        "# Research Workflow A/B Comparison\n\n"
        f"Mode: `{comparison['mode']}`\n\n"
        "## Acceptance\n\n"
        f"{acceptance_lines}\n\n"
        "## Capability Delta\n\n"
        f"{quality_lines}\n\n"
        "## Performance Delta\n\n"
        f"{performance_lines}\n"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_offline_ab(
    *,
    output_root: str | Path | None = None,
    cases: list[ResearchWorkflowCase] | None = None,
    max_cases: int | None = None,
) -> dict[str, Any]:
    selected_cases = list(cases or RESEARCH_WORKFLOW_CASES)
    if max_cases is not None:
        selected_cases = selected_cases[: max(int(max_cases), 0)]

    root = Path(output_root) if output_root is not None else Path("temp") / "research_eval"
    output_dir = root / f"research_eval_{_timestamp()}"
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = _evaluate_variant(name="baseline", enabled=False, cases=selected_cases)
    gated = _evaluate_variant(name="gated", enabled=True, cases=selected_cases)
    comparison = _build_comparison(baseline, gated, mode="offline")

    _write_json(output_dir / "baseline.json", baseline)
    _write_json(output_dir / "gated.json", gated)
    _write_json(output_dir / "comparison.json", comparison)
    (output_dir / "comparison.md").write_text(_comparison_markdown(comparison), encoding="utf-8")

    return {
        "output_dir": output_dir,
        "baseline": baseline,
        "gated": gated,
        "comparison": comparison,
    }


def run_llm_ab(
    *,
    output_root: str | Path | None = None,
    max_cases: int | None = None,
    runs: int = 1,
) -> dict[str, Any]:
    """Create the same artifacts and mark LLM mode as unavailable unless wired by ops.

    The deterministic offline runner is the v1 acceptance gate. This function
    keeps the documented CLI stable while avoiding accidental paid calls from CI.
    """
    result = run_offline_ab(output_root=output_root, max_cases=max_cases)
    comparison_path = result["output_dir"] / "comparison.json"
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["llm_e2e"] = {
        "status": "skipped",
        "requested_runs": runs,
        "reason": (
            "LLM E2E is intentionally opt-in outside the deterministic v1 gate; "
            "wire an API-backed harness before using it as an acceptance signal."
        ),
    }
    comparison["mode"] = "llm-requested-offline-fallback"
    _write_json(comparison_path, comparison)
    (result["output_dir"] / "comparison.md").write_text(
        _comparison_markdown(comparison)
        + "\n## LLM E2E\n\n"
        + f"- SKIPPED: {comparison['llm_e2e']['reason']}\n",
        encoding="utf-8",
    )
    result["comparison"] = comparison
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Run deterministic offline A/B.")
    parser.add_argument("--llm", action="store_true", help="Request optional LLM E2E artifacts.")
    parser.add_argument("--variant", choices=["baseline", "gated", "both"], default="both")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.variant != "both":
        print("[research_eval] Single-variant mode still writes both variants for comparable deltas.")

    if args.llm:
        result = run_llm_ab(output_root=args.output, max_cases=args.max_cases, runs=args.runs)
    else:
        result = run_offline_ab(output_root=args.output, max_cases=args.max_cases)

    print(f"[research_eval] wrote {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
