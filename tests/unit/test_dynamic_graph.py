"""
Dynamic agent graph tests — Level 3 Task→DAG compiler.

Verifies that _build_dynamic_graph() creates only the agents needed
for each task type, and that the handoff topology is correct.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.router_rules import RouterRules


# ── Helper ─────────────────────────────────────────────────────────

def _build_dynamic(query: str) -> dict:
    """Build a dynamic agent graph for a specific query."""
    from core.openai_agentmain import OpenAIOrchestratedAgent

    mock_model = MagicMock()
    orchestrator = OpenAIOrchestratedAgent.__new__(OpenAIOrchestratedAgent)
    orchestrator._active_sdk_model = mock_model
    orchestrator.input_items = []
    orchestrator.history = []
    orchestrator.llm_no = 0
    orchestrator._cached_agent_graph = None
    orchestrator._cached_agent_graph_model_id = None
    orchestrator._run_store = None
    orchestrator._run_classic_executor_task = MagicMock()
    orchestrator._store_executor_result_state = MagicMock()

    with patch.object(OpenAIOrchestratedAgent, "_build_model", return_value=mock_model):
        return orchestrator._build_dynamic_graph(query)


# ── Tests ──────────────────────────────────────────────────────────

class TestDynamicGraphSize:
    """The dynamic graph should create fewer agents for simple tasks."""

    def test_chat_query_has_minimal_agents(self):
        agents = _build_dynamic("你好，今天天气怎么样")
        keys = set(agents.keys())
        # chat + root + executor = 3 (no code/review/research)
        assert "root" in keys
        assert "chat" in keys
        assert "executor" in keys
        assert "code" not in keys
        assert "review" not in keys
        assert "research" not in keys

    def test_code_query_has_code_agent(self):
        agents = _build_dynamic("帮我写一个快速排序")
        keys = set(agents.keys())
        assert "code" in keys
        assert "review" not in keys
        assert "research" not in keys

    def test_review_query_has_review_agent(self):
        agents = _build_dynamic("审查这段代码的安全性")
        keys = set(agents.keys())
        assert "review" in keys
        assert "code" not in keys
        assert "research" not in keys

    def test_research_query_has_research_agent(self):
        agents = _build_dynamic("查一下 Django 5.0 的新特性")
        keys = set(agents.keys())
        assert "research" in keys
        assert "code" not in keys
        assert "review" not in keys

    def test_complex_query_has_multiple_agents(self):
        agents = _build_dynamic("帮我写一个认证模块并审查它的安全性")
        keys = set(agents.keys())
        # Should have both code and review
        assert "code" in keys
        assert "review" in keys

    def test_full_research_to_code_query(self):
        agents = _build_dynamic("查一下 JWT 怎么用然后帮我实现")
        keys = set(agents.keys())
        assert "research" in keys
        assert "code" in keys


class TestDynamicHandoffs:
    """Handoff topology should match the created agents."""

    def test_code_handoffs_to_review_when_both_exist(self):
        agents = _build_dynamic("帮我写代码并审查安全性")
        if "code" in agents and "review" in agents:
            code_handoffs = {h.name for h in agents["code"].handoffs}
            assert "review_agent" in code_handoffs

    def test_no_handoffs_when_only_code(self):
        agents = _build_dynamic("帮我写一个函数")
        if "code" in agents and "review" not in agents:
            assert len(agents["code"].handoffs) == 0

    def test_root_handoffs_match_created_agents(self):
        agents = _build_dynamic("查文档然后写代码然后审查")
        root_handoff_names = {h.name for h in agents["root"].handoffs}
        for key in ("chat", "executor", "code", "review", "research"):
            if key in agents:
                assert agents[key].name in root_handoff_names

    def test_root_never_has_code_agent_when_not_needed(self):
        agents = _build_dynamic("你好")
        root_handoff_names = {h.name for h in agents["root"].handoffs}
        assert "code_agent" not in root_handoff_names
        assert "review_agent" not in root_handoff_names
        assert "research_agent" not in root_handoff_names


class TestDynamicVsStatic:
    """Compare dynamic graph with full static graph."""

    def test_dynamic_graph_smaller_or_equal(self):
        """Dynamic graph should never have more agents than static."""
        from core.openai_agentmain import OpenAIOrchestratedAgent

        mock_model = MagicMock()
        orchestrator = OpenAIOrchestratedAgent.__new__(OpenAIOrchestratedAgent)
        orchestrator._active_sdk_model = mock_model
        orchestrator.input_items = []
        orchestrator.history = []
        orchestrator.llm_no = 0
        orchestrator._cached_agent_graph = None
        orchestrator._cached_agent_graph_model_id = None
        orchestrator._run_store = None
        orchestrator._run_classic_executor_task = MagicMock()
        orchestrator._store_executor_result_state = MagicMock()

        queries = [
            "你好",
            "帮我写代码",
            "审查安全性",
            "查文档",
            "写代码然后审查",
        ]
        with patch.object(OpenAIOrchestratedAgent, "_build_model", return_value=mock_model):
            for q in queries:
                static = orchestrator._build_agent_graph(q, graph_mode="full")
                dynamic = orchestrator._build_dynamic_graph(q)
                assert len(dynamic) <= len(static), (
                    f"Dynamic graph ({len(dynamic)} agents) should be <= "
                    f"static graph ({len(static)} agents) for '{q}'"
                )

    def test_dynamic_graph_always_has_root_executor_chat(self):
        """Every dynamic graph must have root, chat, executor."""
        for q in ["你好", "帮我写代码", "查文档", "审查代码"]:
            agents = _build_dynamic(q)
            assert "root" in agents, f"Missing root for '{q}'"
            assert "executor" in agents, f"Missing executor for '{q}'"
            assert "chat" in agents, f"Missing chat for '{q}'"


class TestDynamicGraphInstructions:
    """Dynamic graph agents should have correct instructions."""

    def test_root_mentions_available_agents(self, agent_graph):
        """Static graph root should mention all agents (existing test, unchanged)."""
        instructions = agent_graph["root"].instructions
        assert "code_agent" in instructions
        assert "review_agent" in instructions
        assert "research_agent" in instructions

    def test_dynamic_root_only_mentions_available(self):
        """Dynamic root should only mention agents that exist."""
        agents = _build_dynamic("你好")
        instructions = agents["root"].instructions
        assert "chat_specialist" in instructions
        assert "planner_executor" in instructions
        assert "code_agent" not in instructions
        assert "review_agent" not in instructions
        assert "research_agent" not in instructions
