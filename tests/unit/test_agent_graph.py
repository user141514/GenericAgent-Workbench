"""
Agent graph structure tests — Level 2: 6-agent mesh topology.

Tests the _build_agent_graph() output including the new cross-handoffs
added in Level 2. Uses shared mock setup from conftest.py.
"""

from __future__ import annotations

import json
import os

import pytest

# ── Paths ──────────────────────────────────────────────────────────

BASELINE_GRAPH_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "baseline_agent_graph.json"
)

AGENT_EXPECTATIONS_V2 = {
    "root": {
        "name": "task_router",
        "has_tools": False,
        "handoff_count": 5,
        "handoff_names": {
            "chat_specialist", "planner_executor",
            "code_agent", "review_agent", "research_agent",
        },
    },
    "chat": {
        "name": "chat_specialist",
        "has_tools": False,
        "handoff_count": 0,
    },
    "executor": {
        "name": "planner_executor",
        "has_tools": True,
        "tool_names": {"run_genericagent_executor"},
        "handoff_count": 0,
    },
    "code": {
        "name": "code_agent",
        "has_tools": True,
        "tool_names": {"run_genericagent_executor"},
        "handoff_count": 2,
        "handoff_names": {"review_agent", "research_agent"},
    },
    "review": {
        "name": "review_agent",
        "has_tools": True,
        "tool_names": {"run_genericagent_executor"},
        "handoff_count": 2,
        "handoff_names": {"code_agent", "research_agent"},
    },
    "research": {
        "name": "research_agent",
        "has_tools": True,
        "tool_names": {"run_genericagent_executor"},
        "handoff_count": 2,
        "handoff_names": {"code_agent", "review_agent"},
    },
}


# ── Helpers ────────────────────────────────────────────────────────

def _extract_agent_info(agent) -> dict:
    """Extract structural info from an agent for comparison."""
    tools = getattr(agent, "tools", []) or []
    handoffs = getattr(agent, "handoffs", []) or []

    tool_names = set()
    for t in tools:
        name = getattr(t, "name", None)
        if name:
            tool_names.add(name)
        elif callable(t):
            tool_names.add(getattr(t, "__name__", "unknown"))

    handoff_names = set()
    for h in handoffs:
        handoff_names.add(getattr(h, "name", "unknown"))

    return {
        "name": getattr(agent, "name", "unknown"),
        "has_tools": len(tool_names) > 0,
        "tool_names": sorted(tool_names),
        "handoff_count": len(handoffs),
        "handoff_names": sorted(handoff_names),
    }


def _record_baseline_graph(agents: dict):
    """Record agent graph structure as baseline."""
    info = {}
    for key, agent in agents.items():
        info[key] = _extract_agent_info(agent)
    os.makedirs(os.path.dirname(BASELINE_GRAPH_PATH), exist_ok=True)
    with open(BASELINE_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


# ── Tests ──────────────────────────────────────────────────────────

class TestAgentGraphStructure:
    """Verify the 6-agent mesh topology with cross-handoffs."""

    def test_graph_has_six_keys(self, agent_graph):
        keys = set(agent_graph.keys())
        assert keys == {"root", "chat", "executor", "code", "review", "research"}

    def test_root_agent_is_task_router(self, agent_graph):
        assert agent_graph["root"].name == "task_router"

    def test_root_has_no_tools(self, agent_graph):
        assert len(agent_graph["root"].tools) == 0

    def test_root_handoffs_to_all_five(self, agent_graph):
        handoff_names = {h.name for h in agent_graph["root"].handoffs}
        assert handoff_names == {
            "chat_specialist", "planner_executor",
            "code_agent", "review_agent", "research_agent",
        }

    def test_code_agent_exists_and_has_tool(self, agent_graph):
        code = agent_graph["code"]
        assert code.name == "code_agent"
        tool_names = {getattr(t, "name", "") for t in code.tools}
        assert "run_genericagent_executor" in tool_names

    def test_code_agent_has_cross_handoffs(self, agent_graph):
        handoff_names = {h.name for h in agent_graph["code"].handoffs}
        assert handoff_names == {"review_agent", "research_agent"}

    def test_review_agent_has_cross_handoffs(self, agent_graph):
        handoff_names = {h.name for h in agent_graph["review"].handoffs}
        assert handoff_names == {"code_agent", "research_agent"}

    def test_research_agent_has_cross_handoffs(self, agent_graph):
        handoff_names = {h.name for h in agent_graph["research"].handoffs}
        assert handoff_names == {"code_agent", "review_agent"}

    def test_planner_executor_is_still_leaf(self, agent_graph):
        assert len(agent_graph["executor"].handoffs) == 0

    def test_chat_specialist_is_still_leaf(self, agent_graph):
        assert len(agent_graph["chat"].handoffs) == 0

    def test_agent_names_are_unique(self, agent_graph):
        names = [a.name for a in agent_graph.values()]
        assert len(names) == len(set(names))

    def test_record_baseline(self, agent_graph):
        info = _record_baseline_graph(agent_graph)
        for key, expected in AGENT_EXPECTATIONS_V2.items():
            actual = info[key]
            assert actual["name"] == expected["name"]
            assert actual["has_tools"] == expected["has_tools"]
            assert actual["handoff_count"] == expected["handoff_count"]
            if "tool_names" in expected:
                assert set(actual["tool_names"]) == expected["tool_names"]
            if "handoff_names" in expected:
                assert set(actual["handoff_names"]) == expected["handoff_names"]
        assert os.path.exists(BASELINE_GRAPH_PATH)


class TestAgentInstructions:
    """Verify agent instructions include handoff guidance (Level 2)."""

    def test_router_forbids_tool_calls(self, agent_graph):
        instructions = agent_graph["root"].instructions
        assert "MUST NOT call any tools" in instructions

    def test_chat_handles_simple_conversation(self, agent_graph):
        instructions = agent_graph["chat"].instructions
        assert "simple conversational requests" in instructions.lower()

    def test_code_agent_knows_handoffs(self, agent_graph):
        instructions = agent_graph["code"].instructions
        assert "hand off to review_agent" in instructions.lower()
        assert "run_genericagent_executor" in instructions

    def test_review_agent_knows_handoffs(self, agent_graph):
        instructions = agent_graph["review"].instructions
        assert "hand off to code_agent" in instructions.lower()
        assert "approval" in instructions.lower() or "pass" in instructions.lower()

    def test_research_agent_knows_handoffs(self, agent_graph):
        instructions = agent_graph["research"].instructions
        assert "hand off to code_agent" in instructions.lower()

    def test_router_mentions_all_agent_types(self, agent_graph):
        instructions = agent_graph["root"].instructions
        for name in ("code_agent", "review_agent", "research_agent", "chat_specialist"):
            assert name in instructions

    def test_executor_agent_still_covers_general_tasks(self, agent_graph):
        instructions = agent_graph["executor"].instructions
        assert "run_genericagent_executor" in instructions
