from __future__ import annotations

import asyncio

from core.openai_runtime.graph_builder import build_minimal_runtime_graph


def test_minimal_graph_builder_returns_runtime_shape_without_orchestrator_imports():
    graph = build_minimal_runtime_graph(
        model=object(),
        original_user_request="review code",
        executor_runner=lambda *args: "ok",
        run_store_getter=lambda: None,
        capability_brief="[capability]",
        behavior_kernel="[kernel]",
        summary_protocol="[summary]",
    )

    assert set(graph) == {"root", "chat", "executor"}
    assert {agent.name for agent in graph["root"].handoffs} == {
        "chat_specialist",
        "planner_executor",
    }
    assert "code_agent" not in graph["root"].instructions
    assert graph["executor"].tools[0].name == "run_genericagent_executor"


def test_minimal_graph_executor_tool_delegates_to_runner_with_run_store():
    calls = []

    def runner(*args):
        calls.append(args)
        return "executor ok"

    graph = build_minimal_runtime_graph(
        model=object(),
        original_user_request="original request",
        executor_runner=runner,
        run_store_getter=lambda: {"store": True},
        executor_progress="progress",
    )

    tool_fn = graph["executor"].tools[0].__wrapped__
    result = asyncio.run(tool_fn("user request", "plan"))

    assert result == "executor ok"
    assert calls == [
        (
            "user request",
            "plan",
            "progress",
            "original request",
            {"store": True},
        )
    ]
