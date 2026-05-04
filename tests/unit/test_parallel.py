"""
Parallel sub-task detection and execution tests — Level 3 advancement.

Tests RouterRules.try_parallel_split() for detecting multi-intent queries
that can be decomposed into independent parallel sub-tasks.
"""

from __future__ import annotations

import pytest

from core.router_rules import RouterRules


class TestParallelDetection:
    """Verify parallel sub-task detection via connector keywords."""

    PARALLEL_QUERIES = [
        ("写前端登录页面同时写后端认证接口", 2, "同时"),
        ("查一下 React 的用法同时写一个示例", 2, "同时"),
        ("审查 auth.py 同时审查 models.py", 2, "同时"),
    ]

    @pytest.mark.parametrize("query,expected_count,connector", PARALLEL_QUERIES)
    def test_parallel_split_by_connector(self, query, expected_count, connector):
        parts = RouterRules.try_parallel_split(query)
        assert parts is not None, f"'{connector}' should trigger parallel split for: {query}"
        assert len(parts) == expected_count, (
            f"Expected {expected_count} parts, got {len(parts)}: {parts}"
        )
        for part in parts:
            assert len(part) >= 3, f"Sub-task too short: '{part}'"

    def test_parallel_split_by_he(self):
        """和 should split when both sides have action verbs."""
        parts = RouterRules.try_parallel_split("写一个登录页面和写一个注册页面")
        assert parts is not None
        assert len(parts) == 2

    def test_he_split_with_shared_verb(self):
        """写A和B pattern: right side may lack explicit verb."""
        parts = RouterRules.try_parallel_split("写一个登录页面和一个注册页面")
        # Right side "一个注册页面" has no action verb → not split
        assert parts is None  # Known limitation: verb must be explicit on both sides

    def test_he_not_split_for_non_actions(self):
        """和 should NOT split when sides lack action verbs."""
        parts = RouterRules.try_parallel_split("Python 和 Java 有什么区别")
        assert parts is None

    NON_PARALLEL_QUERIES = [
        "你好世界",
        "帮我写一个函数",
        "审查这段代码的安全性",
        "查一下 Django 的文档",
        "",  # empty
        "   ",  # whitespace
    ]

    @pytest.mark.parametrize("query", NON_PARALLEL_QUERIES)
    def test_no_false_positive(self, query):
        """Single-intent queries should not trigger parallel split."""
        parts = RouterRules.try_parallel_split(query)
        assert parts is None, f"Should NOT split: '{query}' → {parts}"


class TestParallelSplitRobustness:
    """Edge cases for parallel split."""

    def test_degenerate_connector_alone(self):
        """只包含连接词的查询不应触发"""
        parts = RouterRules.try_parallel_split("同时")
        assert parts is None

    def test_connector_at_edges(self):
        """连接词在开头或结尾"""
        parts = RouterRules.try_parallel_split("同时写代码和审查代码")
        if parts:
            # All parts should have content
            for p in parts:
                assert len(p) >= 3

    def test_subtasks_preserve_order(self):
        parts = RouterRules.try_parallel_split("写前端同时写后端")
        if parts:
            assert "前端" in parts[0]
            assert "后端" in parts[1]

    def test_multiple_connectors(self):
        """多个连接词的查询"""
        parts = RouterRules.try_parallel_split("写前端同时写后端同时写数据库")
        if parts:
            assert len(parts) >= 2
