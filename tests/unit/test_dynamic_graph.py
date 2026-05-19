"""
Dynamic graph tests for the minimal runtime graph.

The current runtime keeps the agent graph minimal for all tasks and uses
routing plus execution mode to decide behavior instead of creating
specialist agent nodes on demand.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.router_rules import RouterRules


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


def _build_static(query: str) -> dict:
    """Build the default runtime graph for a specific query."""
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
        return orchestrator._build_agent_graph(query, graph_mode="full")


RUNTIME_QUERIES = [
    "/chat explain this",
    "/run pytest",
    "/review auth middleware",
    "/research jwt docs",
    "review this bug against the API docs",
]


class TestDynamicGraphShape:
    """The dynamic builder currently returns the same minimal runtime graph."""

    @pytest.mark.parametrize("query", RUNTIME_QUERIES)
    def test_dynamic_graph_has_minimal_runtime_keys(self, query):
        agents = _build_dynamic(query)
        assert set(agents.keys()) == {"root", "chat", "executor"}

    @pytest.mark.parametrize("query", RUNTIME_QUERIES)
    def test_dynamic_graph_never_creates_specialist_keys(self, query):
        agents = _build_dynamic(query)
        assert "code" not in agents
        assert "review" not in agents
        assert "research" not in agents

    @pytest.mark.parametrize("query", RUNTIME_QUERIES)
    def test_dynamic_root_handoffs_are_stable(self, query):
        agents = _build_dynamic(query)
        handoff_names = {handoff.name for handoff in agents["root"].handoffs}
        assert handoff_names == {"chat_specialist", "planner_executor"}


class TestDynamicVsRouting:
    """Routing varies per query even though the runtime graph stays minimal."""

    def test_chat_route_keeps_single_agent_mode(self):
        result = RouterRules.match("/chat explain this")
        assert result.target == "chat"
        assert result.mode == "single_agent"

    def test_mixed_query_can_switch_to_multi_agent_mode_without_specialist_nodes(self):
        result = RouterRules.match("review this bug against the API docs")
        agents = _build_dynamic("review this bug against the API docs")
        assert result.mode == "multi_agent"
        assert set(agents.keys()) == {"root", "chat", "executor"}


class TestDynamicVsStatic:
    """Dynamic and static builders currently use the same runtime graph."""

    @pytest.mark.parametrize("query", RUNTIME_QUERIES)
    def test_dynamic_graph_matches_static_graph_shape(self, query):
        static = _build_static(query)
        dynamic = _build_dynamic(query)
        assert set(dynamic.keys()) == set(static.keys())

    @pytest.mark.parametrize("query", RUNTIME_QUERIES)
    def test_dynamic_root_matches_static_root_handoffs(self, query):
        static = _build_static(query)
        dynamic = _build_dynamic(query)
        static_handoffs = {handoff.name for handoff in static["root"].handoffs}
        dynamic_handoffs = {handoff.name for handoff in dynamic["root"].handoffs}
        assert dynamic_handoffs == static_handoffs


class TestDynamicGraphInstructions:
    """Dynamic graph instructions should reflect the minimal runtime graph."""

    def test_static_root_mentions_only_runtime_agents(self, agent_graph):
        instructions = agent_graph["root"].instructions
        assert "chat_specialist" in instructions
        assert "planner_executor" in instructions
        assert "code_agent" not in instructions
        assert "review_agent" not in instructions
        assert "research_agent" not in instructions

    def test_dynamic_root_mentions_only_runtime_agents(self):
        agents = _build_dynamic("/review auth middleware")
        instructions = agents["root"].instructions
        assert "chat_specialist" in instructions
        assert "planner_executor" in instructions
        assert "code_agent" not in instructions
        assert "review_agent" not in instructions
        assert "research_agent" not in instructions
