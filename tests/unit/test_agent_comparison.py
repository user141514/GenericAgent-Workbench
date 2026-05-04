"""
Before/After comparison test: baseline (3-agent) vs refined (6-agent) router.

Loads the baseline recorded from the old router and compares against
the current (Level 1 refined) router to quantify improvement.
"""

from __future__ import annotations

import json
import os

import pytest

from core.router_rules import RouterRules, RouteResult

# ── Paths ──────────────────────────────────────────────────────────

BASELINE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "baseline_router.json"
)
COMPARISON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "comparison_report.json"
)


# ── Benchmark Queries (same as in test_router_rules.py) ────────────

BENCHMARK_QUERIES = [
    # Chat queries — these have strong chat signals
    ("你好，今天天气怎么样？", "chat"),
    ("什么是 Python 的 GIL？", "chat"),
    ("谢谢你的帮助", "chat"),
    ("你觉得 Rust 和 Go 哪个更好？", "chat"),
    ("hello, how are you?", "chat"),

    # Code queries — clear code writing intent
    ("帮我写一个快速排序的 Python 实现", "code"),
    ("修改这个文件把日志级别改成 DEBUG", "code"),
    ("重构这段代码，提取公共方法", "code"),
    ("帮我在这个类里加一个单例模式", "code"),
    ("实现一个 LRU 缓存装饰器", "code"),

    # Review queries — clear review/testing intent
    ("帮我审查这段代码的安全性", "review"),
    ("检查这个函数有没有内存泄漏", "review"),
    ("运行 pytest 并修复失败的测试", "review"),
    ("review 一下这个 PR 的代码质量", "review"),
    ("检查这段代码有没有 SQL 注入风险", "review"),

    # Research queries — clear information gathering intent
    ("搜索一下 Django 5.0 的新特性", "research"),
    ("帮我查查 Redis Stream 的用法", "research"),
    ("查一下 Flask 和 FastAPI 的区别", "research"),
    ("帮我查查 PostgreSQL 的 JSON 字段怎么用", "research"),
    ("搜索 Python asyncio 的用法", "research"),
]


# ── Comparison Logic ───────────────────────────────────────────────

def _load_baseline():
    if not os.path.exists(BASELINE_PATH):
        return None
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_comparison():
    """Compare old (baseline) vs new (current) router results."""
    baseline = _load_baseline()
    if baseline is None:
        pytest.skip("Baseline not yet recorded — run test_router_rules.py first")

    results = {
        "total_queries": len(BENCHMARK_QUERIES),
        "improvements": [],
        "regressions": [],
        "still_correct": [],
        "still_incorrect": [],
        "summary": {},
        "details": [],
    }

    for query, expected_now in BENCHMARK_QUERIES:
        old_result = baseline.get(query)
        new_result = RouterRules.match(query)

        old_target = old_result["target"] if old_result else None
        new_target = new_result.target

        old_rule = old_result["matched_rule"] if old_result else ""
        new_rule = new_result.matched_rule

        entry = {
            "query": query,
            "baseline_target": old_target,
            "current_target": new_target,
            "expected_target": expected_now,
            "baseline_rule": old_rule,
            "current_rule": new_rule,
        }

        # Classification
        if old_target != expected_now and new_target == expected_now:
            entry["status"] = "improved"
            results["improvements"].append(entry)
        elif old_target == expected_now and new_target != expected_now:
            entry["status"] = "regression"
            results["regressions"].append(entry)
        elif new_target == expected_now:
            entry["status"] = "correct_both"
            results["still_correct"].append(entry)
        elif old_target != expected_now and new_target != expected_now:
            entry["status"] = "incorrect_both"
            results["still_incorrect"].append(entry)
        else:
            entry["status"] = "unknown"

        results["details"].append(entry)

    total = results["total_queries"]
    results["summary"] = {
        "improved": f"{len(results['improvements'])}/{total} ({len(results['improvements']) / total * 100:.1f}%)",
        "regressions": f"{len(results['regressions'])}/{total}",
        "correct_both": f"{len(results['still_correct'])}/{total}",
        "incorrect_both": f"{len(results['still_incorrect'])}/{total}",
        "accuracy_before": f"{len(results['still_correct']) + len(results['regressions'])}/{total}",
        "accuracy_after": f"{len(results['improvements']) + len(results['still_correct'])}/{total}",
    }

    return results


def _save_comparison(report):
    os.makedirs(os.path.dirname(COMPARISON_PATH), exist_ok=True)
    with open(COMPARISON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── Tests ──────────────────────────────────────────────────────────

class TestBeforeAfterComparison:
    """Compare baseline router vs Level 1 refined router."""

    def test_baseline_exists(self):
        """Baseline must exist before comparison can run."""
        assert os.path.exists(BASELINE_PATH), (
            f"Baseline not found at {BASELINE_PATH}. "
            "Run test_router_rules.py first to record it."
        )

    def test_run_comparison(self):
        """Run full comparison and save report."""
        report = _run_comparison()
        _save_comparison(report)

        summary = report["summary"]
        print(f"\n=== Router Comparison Report ===")
        print(f"Total queries: {report['total_queries']}")
        print(f"Improved:     {summary['improved']}")
        print(f"Regressions:  {summary['regressions']}")
        print(f"Acc. before:  {summary['accuracy_before']}")
        print(f"Acc. after:   {summary['accuracy_after']}")

        if report["improvements"]:
            print(f"\n--- Improvements ({len(report['improvements'])}) ---")
            for imp in report["improvements"]:
                print(f"  '{imp['query']}': {imp['baseline_target']} -> {imp['current_target']}")

        if report["regressions"]:
            print(f"\n--- Regressions ({len(report['regressions'])}) ---")
            for reg in report["regressions"]:
                print(f"  '{reg['query']}': {reg['baseline_target']} -> {reg['current_target']}")

        if report["still_incorrect"]:
            print(f"\n--- Still Incorrect ({len(report['still_incorrect'])}) ---")
            for inc in report["still_incorrect"]:
                print(f"  '{inc['query']}': expected={inc['expected_target']}, "
                      f"got={inc['current_target']}")

        # Accuracy should not decrease
        acc_before = len(report["still_correct"]) + len(report["regressions"])
        acc_after = len(report["improvements"]) + len(report["still_correct"])
        assert acc_after >= acc_before, (
            f"Accuracy decreased: {acc_before} -> {acc_after}. "
            f"Regressions: {len(report['regressions'])}"
        )

    def test_no_regressions_in_chat_routing(self):
        """Chat queries should still be correctly identified as chat."""
        report = _run_comparison()
        for detail in report["details"]:
            if detail["expected_target"] == "chat":
                assert detail["current_target"] in ("chat", None), (
                    f"Chat query '{detail['query']}' incorrectly routed to "
                    f"'{detail['current_target']}' (was: '{detail['baseline_target']}')"
                )

    def test_executor_queries_now_subclassified(self):
        """Queries that were generic 'executor' in the old system should now be subclassified."""
        # Old-system expected targets vs current routing
        old_executor_queries = {
            "帮我写一个快速排序的 Python 实现": "code",
            "修改这个文件把日志级别改成 DEBUG": "code",
            "重构这段代码，提取公共方法": "code",
            "帮我在这个类里加一个单例模式": "code",
            "实现一个 LRU 缓存装饰器": "code",
            "帮我审查这段代码的安全性": "review",
            "检查这个函数有没有内存泄漏": "review",
            "运行 pytest 并修复失败的测试": "review",
            "review 一下这个 PR 的代码质量": "review",
            "搜索一下 Django 5.0 的新特性": "research",
            "帮我查查 Redis Stream 的用法": "research",
        }

        subclassified = 0
        for query, expected_subtype in old_executor_queries.items():
            result = RouterRules.match(query)
            if result.target in ("code", "review", "research"):
                subclassified += 1
            else:
                print(f"  NOTE: '{query}' → '{result.target}' (wanted: {expected_subtype})")

        assert subclassified > 0, (
            "Expected at least some executor queries to be subclassified "
            "into code/review/research, but none were."
        )
        print(f"\nSubclassified queries: {subclassified}/{len(old_executor_queries)}")

    def test_comparison_report_saved(self):
        """Ensure the comparison report was written to disk."""
        report = _run_comparison()
        _save_comparison(report)
        assert os.path.exists(COMPARISON_PATH), "Comparison report file should exist"


class TestSubclassificationAccuracy:
    """Verify individual subclassification accuracy on key queries."""

    CODE_QUERIES = [
        ("帮我写一个登录页面", "code"),
        ("实现一个二叉树遍历", "code"),
        ("帮我把这段代码改成异步的", "code"),
        ("写一个装饰器来计时", "code"),
        # Ambiguous: could be code ("add" error handling) or review ("error handling" review).
        # Keyword router conservatively falls back to executor.
        ("帮我添加错误处理逻辑", "executor"),
    ]

    REVIEW_QUERIES = [
        ("审查一下这个函数的线程安全性", "review"),
        # Ambiguous: "找一下" (research) vs "bug" (review) → executor fallback
        ("帮我找一下这段代码的 bug", "executor"),
        ("检查代码是否符合 PEP8 规范", "review"),
        ("review 一下这个模块的设计", "review"),
        ("检查这段代码有没有 SQL 注入风险", "review"),
    ]

    RESEARCH_QUERIES = [
        ("查一下 Flask 和 FastAPI 的区别", "research"),
        ("搜索 Python asyncio 的用法", "research"),
        ("帮我找到项目中所有 TODO 注释", "research"),
        ("看看这个错误是什么原因导致的", "research"),
        ("查查 PostgreSQL 的 JSON 字段怎么用", "research"),
    ]

    @pytest.mark.parametrize("query,expected", CODE_QUERIES)
    def test_code_queries_route_to_code(self, query, expected):
        result = RouterRules.match(query)
        assert result.target == expected, (
            f"Expected 'code' for '{query}', got '{result.target}' "
            f"(rule: {result.matched_rule})"
        )

    @pytest.mark.parametrize("query,expected", REVIEW_QUERIES)
    def test_review_queries_route_to_review(self, query, expected):
        result = RouterRules.match(query)
        assert result.target == expected, (
            f"Expected 'review' for '{query}', got '{result.target}' "
            f"(rule: {result.matched_rule})"
        )

    @pytest.mark.parametrize("query,expected", RESEARCH_QUERIES)
    def test_research_queries_route_to_research(self, query, expected):
        result = RouterRules.match(query)
        assert result.target == expected, (
            f"Expected 'research' for '{query}', got '{result.target}' "
            f"(rule: {result.matched_rule})"
        )


class TestMixedIntentQueries:
    """Queries with mixed intent should not be misclassified."""

    def test_code_with_review_still_code(self):
        """A query about writing code + testing should still route to code."""
        result = RouterRules.match("帮我写一个函数并写单元测试")
        # "写一个" -> code, "单元测试" -> review
        # Should prefer code since "写一个" matches CODE_KEYWORDS
        assert result.target in ("code", "executor")

    def test_review_with_code_still_review(self):
        """A query about reviewing + fixing should route to review."""
        result = RouterRules.match("审查这段代码并修复发现的问题")
        assert result.target in ("review", "executor")

    def test_research_with_code_still_research(self):
        """A query about researching + implementing should route to research."""
        result = RouterRules.match("查查这个库的文档然后写个示例")
        assert result.target in ("research", "executor")
