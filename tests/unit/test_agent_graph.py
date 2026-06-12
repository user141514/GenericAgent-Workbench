"""
Minimal runtime graph structure tests.

These tests validate the graph shape the runtime actually uses today:
one router plus two leaf agents.
"""

from __future__ import annotations

import json
import os


BASELINE_GRAPH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "baseline_agent_graph.json"
)

AGENT_EXPECTATIONS = {
    "root": {
        "name": "task_router",
        "has_tools": False,
        "handoff_count": 2,
        "handoff_names": {"chat_specialist", "planner_executor"},
    },
    "chat": {
        "name": "chat_specialist",
        "has_tools": False,
        "handoff_count": 0,
        "handoff_names": set(),
    },
    "executor": {
        "name": "planner_executor",
        "has_tools": True,
        "tool_names": {"run_genericagent_executor"},
        "handoff_count": 0,
        "handoff_names": set(),
    },
}


def _extract_agent_info(agent) -> dict:
    """Extract structural info from an agent for comparison."""
    tools = getattr(agent, "tools", []) or []
    handoffs = getattr(agent, "handoffs", []) or []

    tool_names = set()
    for tool in tools:
        name = getattr(tool, "name", None)
        if name:
            tool_names.add(name)
        elif callable(tool):
            tool_names.add(getattr(tool, "__name__", "unknown"))

    handoff_names = set()
    for handoff in handoffs:
        handoff_names.add(getattr(handoff, "name", "unknown"))

    return {
        "name": getattr(agent, "name", "unknown"),
        "has_tools": len(tool_names) > 0,
        "tool_names": sorted(tool_names),
        "handoff_count": len(handoffs),
        "handoff_names": sorted(handoff_names),
    }


def _record_baseline_graph(agents: dict) -> dict:
    """Record agent graph structure as baseline."""
    info = {}
    for key, agent in agents.items():
        info[key] = _extract_agent_info(agent)
    os.makedirs(os.path.dirname(BASELINE_GRAPH_PATH), exist_ok=True)
    with open(BASELINE_GRAPH_PATH, "w", encoding="utf-8") as handle:
        json.dump(info, handle, ensure_ascii=False, indent=2)
    return info


class TestAgentGraphStructure:
    """Verify the minimal runtime graph topology."""

    def test_graph_has_three_keys(self, agent_graph):
        keys = set(agent_graph.keys())
        assert keys == {"root", "chat", "executor"}

    def test_root_agent_is_task_router(self, agent_graph):
        assert agent_graph["root"].name == "task_router"

    def test_root_has_no_tools(self, agent_graph):
        assert len(agent_graph["root"].tools) == 0

    def test_root_handoffs_to_chat_and_executor(self, agent_graph):
        handoff_names = {handoff.name for handoff in agent_graph["root"].handoffs}
        assert handoff_names == {"chat_specialist", "planner_executor"}

    def test_chat_agent_is_leaf(self, agent_graph):
        chat = agent_graph["chat"]
        assert chat.name == "chat_specialist"
        assert len(chat.tools) == 0
        assert len(chat.handoffs) == 0

    def test_executor_agent_has_single_runtime_tool(self, agent_graph):
        executor = agent_graph["executor"]
        assert executor.name == "planner_executor"
        tool_names = {getattr(tool, "name", "") for tool in executor.tools}
        assert tool_names == {"run_genericagent_executor"}

    def test_executor_agent_is_leaf(self, agent_graph):
        assert len(agent_graph["executor"].handoffs) == 0

    def test_agent_names_are_unique(self, agent_graph):
        names = [agent.name for agent in agent_graph.values()]
        assert len(names) == len(set(names))

    def test_record_baseline(self, agent_graph):
        info = _record_baseline_graph(agent_graph)
        for key, expected in AGENT_EXPECTATIONS.items():
            actual = info[key]
            assert actual["name"] == expected["name"]
            assert actual["has_tools"] == expected["has_tools"]
            assert actual["handoff_count"] == expected["handoff_count"]
            assert set(actual["handoff_names"]) == expected["handoff_names"]
            if "tool_names" in expected:
                assert set(actual["tool_names"]) == expected["tool_names"]
        assert os.path.exists(BASELINE_GRAPH_PATH)


class TestAgentInstructions:
    """Verify agent instructions match the minimal runtime behavior."""

    def test_router_forbids_tool_calls(self, agent_graph):
        instructions = agent_graph["root"].instructions
        assert "have NO tools" in instructions
        assert "do not attempt to call any tools" in instructions

    def test_router_mentions_only_runtime_agents(self, agent_graph):
        instructions = agent_graph["root"].instructions
        assert "chat_specialist" in instructions
        assert "planner_executor" in instructions
        assert "code_agent" not in instructions
        assert "review_agent" not in instructions
        assert "research_agent" not in instructions

    def test_chat_handles_simple_conversation(self, agent_graph):
        instructions = agent_graph["chat"].instructions.lower()
        assert "simple conversational requests" in instructions
        assert "do not require tool use" in instructions

    def test_executor_handles_all_non_chat_work(self, agent_graph):
        instructions = agent_graph["executor"].instructions
        assert "all non-chat execution tasks" in instructions
        assert "code, review, research, and mixed multi-step work" in instructions
        assert "run_genericagent_executor" in instructions

    def test_runtime_agents_include_shared_behavior_kernel(self, agent_graph):
        for key in ("chat", "executor"):
            instructions = agent_graph[key].instructions
            assert "Shared Behavior Kernel" in instructions
            assert "calm, warm, plainspoken" in instructions
            assert "avoid performative certainty" in instructions
            assert "Evidence first" in instructions
            assert "Execution honesty" in instructions
            assert "Memory discipline" in instructions
            assert "facts, assumptions" in instructions
