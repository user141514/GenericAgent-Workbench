"""
Pipeline multi-hop tests — Level 2 agent communication patterns.

Verifies that the handoff topology supports pipelines (code→review→code),
research→code chains, and that leaf agents remain properly isolated.

Uses the shared `agent_graph` fixture from conftest.py.
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

class TestPipelineTopology:
    """Verify the mesh topology supports common pipeline patterns."""

    def test_code_review_cycle_exists(self, agent_graph):
        code = agent_graph["code"]
        review = agent_graph["review"]
        assert "review_agent" in _handoff_names(code), "code→review missing"
        assert "code_agent" in _handoff_names(review), "review→code missing"

    def test_code_to_research_chain(self, agent_graph):
        assert "research_agent" in _handoff_names(agent_graph["code"])

    def test_review_to_research_chain(self, agent_graph):
        assert "research_agent" in _handoff_names(agent_graph["review"])

    def test_research_to_code_chain(self, agent_graph):
        assert "code_agent" in _handoff_names(agent_graph["research"])

    def test_research_to_review_chain(self, agent_graph):
        assert "review_agent" in _handoff_names(agent_graph["research"])

    def test_full_pipeline_path(self, agent_graph):
        """code→review→code→review fix-verify cycle is reachable."""
        reachable = _all_reachable(agent_graph, "code")
        assert "review_agent" in reachable
        assert "code_agent" in reachable  # self
        assert "research_agent" in reachable

    def test_research_pipeline_path(self, agent_graph):
        """research→code→review (find→implement→verify)."""
        reachable = _all_reachable(agent_graph, "research")
        assert "code_agent" in reachable
        assert "review_agent" in reachable


class TestLeafAgentIsolation:
    """Verify that leaf agents remain properly isolated."""

    def test_planner_executor_is_leaf(self, agent_graph):
        assert len(agent_graph["executor"].handoffs) == 0

    def test_chat_specialist_is_leaf(self, agent_graph):
        assert len(agent_graph["chat"].handoffs) == 0

    def test_planner_unreachable_from_code(self, agent_graph):
        assert "planner_executor" not in _handoff_names(agent_graph["code"])

    def test_planner_unreachable_from_review(self, agent_graph):
        assert "planner_executor" not in _handoff_names(agent_graph["review"])

    def test_chat_unreachable_from_all_executors(self, agent_graph):
        for key in ("code", "review", "research"):
            assert "chat_specialist" not in _handoff_names(agent_graph[key])


class TestPipelineInstructions:
    """Verify agent instructions guide correct handoff decisions."""

    def test_code_agent_knows_to_handoff_to_review(self, agent_graph):
        assert "hand off to review_agent" in agent_graph["code"].instructions.lower()

    def test_review_agent_knows_to_handoff_to_code(self, agent_graph):
        assert "hand off to code_agent" in agent_graph["review"].instructions.lower()

    def test_review_agent_knows_approval_path(self, agent_graph):
        inst = agent_graph["review"].instructions.lower()
        assert "approval" in inst or "pass" in inst

    def test_research_agent_knows_to_handoff_to_code(self, agent_graph):
        assert "hand off to code_agent" in agent_graph["research"].instructions.lower()

    def test_research_agent_knows_stop_condition(self, agent_graph):
        inst = agent_graph["research"].instructions.lower()
        assert "final answer" in inst or "present your findings" in inst

    def test_all_executors_mention_handoffs(self, agent_graph):
        for key in ("code", "review", "research"):
            assert "handoff" in agent_graph[key].instructions.lower()


class TestMaxHopConstraint:
    """Verify practical pipeline depth constraints."""

    def test_max_hops_from_root(self, agent_graph):
        reachable = _all_reachable(agent_graph, "root", max_hops=4)
        assert len(reachable) <= 6

    def test_code_review_cycle_has_exit(self, agent_graph):
        """code_agent has two handoff options (review + research)."""
        assert len(agent_graph["code"].handoffs) == 2
