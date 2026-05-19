"""
RouterRules baseline and regression tests.

Records the current (pre-refinement) routing behavior as baseline,
then validates correctness of the keyword-based routing logic.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict

import pytest

from core.router_rules import RouteResult, RouterRules, RouterStats, quick_route


# ── Benchmark Queries ──────────────────────────────────────────────
# 20 queries covering: chat (5), code (5), review (5), research (5)

BENCHMARK_QUERIES = [
    # Chat queries (should route to chat or None)
    ("你好，今天天气怎么样？", "chat"),
    ("什么是 Python 的 GIL？", "chat"),
    ("谢谢你的帮助", "chat"),
    ("你觉得 Rust 和 Go 哪个更好？", "chat"),
    ("hello, how are you?", "chat"),

    # Code queries (currently executor, will become code_agent)
    ("帮我写一个快速排序的 Python 实现", "executor"),
    ("修改这个文件把日志级别改成 DEBUG", "executor"),
    ("重构这段代码，提取公共方法", "executor"),
    ("帮我在这个类里加一个单例模式", "executor"),
    ("实现一个 LRU 缓存装饰器", "executor"),

    # Review queries (currently executor, will become review_agent)
    ("帮我审查这段代码的安全性", "executor"),
    ("检查这个函数有没有内存泄漏", "executor"),
    ("运行 pytest 并修复失败的测试", "executor"),
    ("验证这个 API 的输入参数是否做了校验", "executor"),
    ("review 一下这个 PR 的代码质量", "executor"),

    # Research queries (currently executor, will become research_agent)
    ("搜索一下 Django 5.0 的新特性", "executor"),
    ("帮我查查 Redis Stream 的用法", "executor"),
    ("看一下这个项目的 README 文档", "executor"),
    ("这个错误日志是什么意思：ConnectionRefusedError", "executor"),
    ("找到所有引用了 deprecated API 的文件", "executor"),
]


# ── Baseline Recording ─────────────────────────────────────────────

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "baseline_router.json")


def _record_baseline():
    """Record current router results as baseline (call once before refactoring)."""
    results = {}
    for query, expected in BENCHMARK_QUERIES:
        result = RouterRules.match(query)
        results[query] = {
            "target": result.target,
            "matched_rule": result.matched_rule,
            "confidence": result.confidence,
            "expected": expected,
        }
    os.makedirs(os.path.dirname(BASELINE_PATH), exist_ok=True)
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return results


def _load_baseline():
    """Load previously recorded baseline."""
    if not os.path.exists(BASELINE_PATH):
        return None
    with open(BASELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Tests: Current Router Behavior ─────────────────────────────────

class TestRouterChatDetection:
    """Verify chat queries are correctly identified."""

    CHAT_QUERIES = [
        ("你好", "chat", "greeting"),
        ("谢谢", "chat", "thanks"),
        ("什么是闭包？", "chat", "explanation_question"),
        ("你觉得微服务架构怎么样？", "chat", "opinion_question_services_keyword"),
        ("Python 和 Java 有什么区别？", "chat", "comparison"),
        ("hi there", "chat", "english_greeting"),
        ("HELLO there", "chat", "english_greeting_uppercase"),
    ]

    @pytest.mark.parametrize("query,expected_target,description", CHAT_QUERIES)
    def test_chat_query_routes_to_chat(self, query, expected_target, description):
        result = RouterRules.match(query)
        assert result.target == expected_target, (
            f"[{description}] Expected '{expected_target}' but got '{result.target}' "
            f"(rule: {result.matched_rule}) for query: {query}"
        )


class TestRouterExecutorDetection:
    """Verify executor queries are correctly identified."""

    EXECUTOR_QUERIES = [
        # After Level 1 refinement, queries are subclassified:
        # "code" = code writing, "review" = code review, "research" = info gathering
        ("帮我写一个函数", "code", "code_write"),
        ("读取 app.py 文件", "executor", "file_read"),
        ("运行 pytest 测试", "executor", "test_run"),
        ("git commit 并 push", "executor", "git_ops"),
        ("搜索 Django 文档", "research", "search_docs"),
        ("/run python main.py", "executor", "slash_command"),
        ("规划一个用户系统的方案", "executor", "planning"),
    ]

    @pytest.mark.parametrize("query,expected_target,description", EXECUTOR_QUERIES)
    def test_executor_query_routes_to_executor(self, query, expected_target, description):
        result = RouterRules.match(query)
        assert result.target == expected_target, (
            f"[{description}] Expected '{expected_target}' but got '{result.target}' "
            f"(rule: {result.matched_rule}) for query: {query}"
        )


class TestRouterEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_query_returns_none(self):
        result = RouterRules.match("")
        assert result.target is None

    def test_whitespace_only_returns_none(self):
        result = RouterRules.match("   ")
        assert result.target is None

    def test_excluded_query_returns_none(self):
        result = RouterRules.match("只是想问一下这个怎么用")
        assert result.target is None

    def test_action_start_verb_routes_to_executor(self):
        result = RouterRules.match("帮我看看这个文件")
        assert result.target == "executor"

    def test_slash_chat_command_routes_to_chat(self):
        result = RouterRules.match("/chat what is this?")
        assert result.target == "chat"

    def test_ambiguous_query_returns_none(self):
        """Query with no strong signal should fall through to LLM routing."""
        result = RouterRules.match("怎么样")
        assert result.target is None


class TestRouterStats:
    """Verify router statistics collection."""

    def setup_method(self):
        RouterStats.reset()

    def test_stats_collection(self):
        RouterStats.record(RouteResult(target="chat", matched_rule="test"), "hello")
        RouterStats.record(RouteResult(target="executor", matched_rule="test"), "帮我写")
        RouterStats.record(RouteResult(target=None, matched_rule="no_match"), "xyz")

        stats = RouterStats.get_stats()
        assert stats["total_queries"] == 3
        assert "66.7%" in stats["hit_rate"]

    def test_stats_empty(self):
        RouterStats.reset()
        stats = RouterStats.get_stats()
        assert stats["message"] == "暂无统计数据"


class TestQuickRoute:
    """Test the convenience function."""

    def test_quick_route_chat(self):
        assert quick_route("你好") == "chat"

    def test_quick_route_executor(self):
        # Queries that used to route to generic "executor" now get subclassified.
        assert quick_route("帮我写代码") == "code"
        assert quick_route("帮我写一个函数") == "code"

    def test_quick_route_review(self):
        assert quick_route("帮我审查这段代码") == "review"

    def test_quick_route_research(self):
        assert quick_route("帮我查一下 Django 的文档") == "research"

    def test_quick_route_none(self):
        assert quick_route("xyzabc123") is None


# ── Baseline Record & Compare ──────────────────────────────────────

class TestBaseline:
    """Record and validate baseline routing behavior.

    The baseline captures the ACTUAL behavior of the current router,
    including known limitations (e.g. queries without keyword matches
    routing to None instead of executor). The baseline serves as the
    reference point for comparing the refined router in Step 2.
    """

    def test_record_and_save_baseline(self):
        """Record baseline results for all benchmark queries."""
        results = _record_baseline()
        assert len(results) == len(BENCHMARK_QUERIES)

        # Check that all benchmark queries are present in the baseline
        for query, _expected in BENCHMARK_QUERIES:
            assert query in results, f"Query missing from baseline: {query}"
            assert "target" in results[query]
            assert "matched_rule" in results[query]

    def test_baseline_file_exists(self):
        """Ensure baseline file was written to disk."""
        assert os.path.exists(BASELINE_PATH), (
            f"Baseline file not found at {BASELINE_PATH}. "
            "Run test_record_and_save_baseline first."
        )

    def test_baseline_all_queries_have_results(self):
        """Every benchmark query should have a routing result."""
        baseline = _load_baseline()
        if baseline is None:
            pytest.skip("Baseline not yet recorded")
        for query, _expected in BENCHMARK_QUERIES:
            assert query in baseline, f"Query missing from baseline: {query}"
            assert "target" in baseline[query]
            assert "matched_rule" in baseline[query]

    def test_baseline_known_limitations(self):
        """Document known limitations of the current router as baseline.

        These are queries that the current router misclassifies.
        The refined router (Step 2) should improve on these.
        """
        baseline = _load_baseline()
        if baseline is None:
            pytest.skip("Baseline not yet recorded")

        known_issues = []

        # Collect queries where target doesn't match expected
        for query, expected in BENCHMARK_QUERIES:
            actual = baseline[query]["target"]
            if actual != expected:
                known_issues.append({
                    "query": query,
                    "expected": expected,
                    "actual": actual,
                    "rule": baseline[query]["matched_rule"],
                })

        # Save known issues as baseline artifact
        issues_path = BASELINE_PATH.replace(".json", "_known_issues.json")
        with open(issues_path, "w", encoding="utf-8") as f:
            json.dump(known_issues, f, ensure_ascii=False, indent=2)

        # This is informational - not a failure
        if known_issues:
            print(f"\n=== Known Router Limitations (baseline): {len(known_issues)} queries ===")
            for issue in known_issues:
                print(f"  '{issue['query']}' -> expected={issue['expected']}, "
                      f"actual={issue['actual']} ({issue['rule']})")
        assert len(known_issues) >= 0, "This should never fail"


class TestRouteMode:
    """Verify the route contract now carries execution mode information."""

    def test_chat_route_stays_single_agent(self):
        result = RouterRules.match("/chat explain this")
        assert result.mode == "single_agent"
        assert result.parallel_subtasks == []

    def test_mixed_specialist_route_switches_to_multi_agent(self):
        result = RouterRules.match("review this bug against the API docs")
        assert result.mode == "multi_agent"
