from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


def build_minimal_runtime_graph(
    *,
    model: Any,
    original_user_request: str,
    executor_runner: Callable[..., Any],
    run_store_getter: Callable[[], Any],
    executor_progress: Any = None,
    capability_brief: str = "",
    behavior_kernel: str = "",
    summary_protocol: str = "",
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the active OpenAI runtime graph.

    This module owns graph shape only. The caller owns model construction,
    caching, and OpenAI SDK path setup, which keeps this boundary portable for a
    future non-Python runtime.

    Args:
        profiles: Optional dict of capability profile name -> CapabilityProfile.
                  When provided, ``build_agent_instructions()`` is used instead
                  of the hardcoded instruction strings for each agent.
    """

    from agents import Agent, function_tool
    from core.agents.capability_profile import build_agent_instructions

    common = {"model": model}

    # ── Agent instructions: profile-driven or hardcoded ──
    if profiles is not None:
        chat_profile = profiles.get("chat_specialist") or profiles.get("default")
        planner_profile = profiles.get("planner_executor") or profiles.get("default")
        chat_instructions = (
            build_agent_instructions(chat_profile)
            if chat_profile
            else "Handle simple conversation requests."
        )
        planner_instructions = (
            build_agent_instructions(planner_profile)
            if planner_profile
            else "Handle all non-chat execution tasks."
        )
    else:
        chat_instructions = (
            f"{capability_brief}"
            f"{behavior_kernel}"
            "You handle simple conversational requests that do not require tool use. "
            "If asked about tools or skills, explain that this app can delegate execution to "
            "the classic GenericAgent executor through the workflow coordinator. "
            "Be concise, helpful, and avoid inventing actions you did not take.\n\n"
            f"{summary_protocol}"
        )
        planner_instructions = (
            f"{capability_brief}"
            f"{behavior_kernel}"
            "You handle all non-chat execution tasks in this runtime, including code, review, "
            "research, and mixed multi-step work.\n"
            "1. FIRST create a short, actionable plan (2-5 steps)\n"
            "2. Call run_genericagent_executor to execute the plan\n"
            "3. AFTER execution, ALWAYS verify results:\n"
            "   - Did the execution achieve all goals?\n"
            "   - Is there already a usable answer or evidence?\n"
            "   - Only retry if the first run produced no usable findings at all.\n"
            "4. End with: Plan, Execution Summary, Verification, Final Answer\n\n"
            "IMPORTANT: You have only ONE tool: run_genericagent_executor. "
            "All file/code/browser operations happen inside the executor.\n\n"
            f"{summary_protocol}"
        )

    chat_agent = Agent(
        name="chat_specialist",
        handoff_description="Handle simple conversation or explanation-only requests.",
        instructions=chat_instructions,
        **common,
    )

    @function_tool(name_override="run_genericagent_executor")
    async def run_genericagent_executor(user_request: str, execution_plan: str) -> str:
        """Delegate execution to the classic GenericAgent runtime."""
        return await asyncio.to_thread(
            executor_runner,
            user_request,
            execution_plan,
            executor_progress,
            original_user_request,
            run_store_getter(),
        )

    planner_executor_agent = Agent(
        name="planner_executor",
        handoff_description="General-purpose planner and executor for all non-chat tasks.",
        instructions=planner_instructions,
        tools=[run_genericagent_executor],
        **common,
    )

    root_agent = Agent(
        name="task_router",
        instructions=(
            "You are a router. You have NO tools - do not attempt to call any tools.\n"
            "Your ONLY job is to transfer to the appropriate agent via handoffs.\n"
            "- Simple chat or conversation -> chat_specialist\n"
            "- Any file/code/browser/research/review/multi-step task -> planner_executor\n"
        ),
        handoffs=[chat_agent, planner_executor_agent],
        **common,
    )
    return {
        "root": root_agent,
        "chat": chat_agent,
        "executor": planner_executor_agent,
    }


__all__ = ["build_minimal_runtime_graph"]
