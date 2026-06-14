"""
Pipeline tests — verify the active {root, chat, executor} handoff topology.

Uses the shared `agent_graph` fixture from tests/conftest.py.
"""

from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────

def _handoff_names(agent):
    return {h.name for h in agent.handoffs}

def _all_reachable(agents, start_key, max_hops=5):
    """BFS: all agent names reachable from start_key via handoffs."""
    visited = set()
    queue = [(agents[start_key], 0)]
    while queue:
        agent, depth = queue.pop(0)
        if agent.name in visited or depth > max_hops:
            continue
        visited.add(agent.name)
        for h in agent.handoffs:
            if h.name not in visited:
                queue.append((h, depth + 1))
    return visited


# ── Tests ──────────────────────────────────────────────────────────

class TestGraphKeys:
    """The active graph contains exactly root, chat, executor."""

    def test_expected_keys_exist(self, agent_graph):
        assert set(agent_graph.keys()) == {"root", "chat", "executor"}

    def test_agent_names_match_keys(self, agent_graph):
        assert agent_graph["root"].name == "task_router"
        assert agent_graph["chat"].name == "chat_specialist"
        assert agent_graph["executor"].name == "planner_executor"


class TestHandoffTopology:
    """Root routes to chat and executor; leaves have no agent handoffs."""

    def test_root_handoffs_to_both_leaves(self, agent_graph):
        assert _handoff_names(agent_graph["root"]) == {"chat_specialist", "planner_executor"}

    def test_chat_is_leaf(self, agent_graph):
        assert len(agent_graph["chat"].handoffs) == 0

    def test_executor_is_leaf(self, agent_graph):
        assert len(agent_graph["executor"].handoffs) == 0

    def test_both_leaves_reachable_from_root(self, agent_graph):
        reachable = _all_reachable(agent_graph, "root")
        assert "chat_specialist" in reachable
        assert "planner_executor" in reachable


class TestRoutingInstructions:
    """Root instructions guide correct handoff decisions."""

    def test_root_mentions_chat_specialist(self, agent_graph):
        inst = agent_graph["root"].instructions.lower()
        assert "chat_specialist" in inst

    def test_root_mentions_planner_executor(self, agent_graph):
        inst = agent_graph["root"].instructions.lower()
        assert "planner_executor" in inst

    def test_chat_knows_it_is_conversation_only(self, agent_graph):
        inst = agent_graph["chat"].instructions.lower()
        assert "conversation" in inst or "chat" in inst

    def test_executor_knows_multi_step_tasks(self, agent_graph):
        inst = agent_graph["executor"].instructions.lower()
        assert "plan" in inst
        assert "verify" in inst

    def test_executor_has_run_tool_not_handoff(self, agent_graph):
        """executor delegates via tool, not agent handoff."""
        assert len(agent_graph["executor"].handoffs) == 0
        tool_names = [t.name for t in (agent_graph["executor"].tools or [])]
        assert "run_genericagent_executor" in tool_names


class TestMaxHopConstraint:
    """Shallow graph — reachable set is small."""

    def test_max_hops_from_root(self, agent_graph):
        reachable = _all_reachable(agent_graph, "root", max_hops=4)
        assert len(reachable) <= 3
        assert reachable == {"task_router", "chat_specialist", "planner_executor"}