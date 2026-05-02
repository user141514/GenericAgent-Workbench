from __future__ import annotations

from dataclasses import dataclass, field

from core.skills.skill_phase import normalize_skill_phase
from core.skills.skill_registry import SkillRegistry


@dataclass
class ExecutionPolicy:
    enabled_agents: set[str] | None = None
    disabled_agents: set[str] = field(default_factory=set)
    preferred_agents: list[str] = field(default_factory=list)
    enabled_tools: set[str] | None = None
    disabled_tools: set[str] = field(default_factory=set)
    preferred_tools: list[str] = field(default_factory=list)
    suppressed_context_sections: set[str] = field(default_factory=set)
    enabled_context_sections: set[str] = field(default_factory=set)
    route_override: str | None = None
    tool_schema_policy: str | None = None
    context_policy: str | None = None
    enabled_shortcuts: set[str] = field(default_factory=set)
    disabled_shortcuts: set[str] = field(default_factory=set)
    max_turns: int | None = None
    max_llm_calls: int | None = None
    max_tool_calls: int | None = None
    max_prompt_chars: int | None = None
    max_skill_chars: int | None = None
    source_skills: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def execution_policy_to_dict(policy: ExecutionPolicy) -> dict:
    return {
        "enabled_agents": sorted(policy.enabled_agents) if policy.enabled_agents is not None else None,
        "disabled_agents": sorted(policy.disabled_agents),
        "preferred_agents": list(policy.preferred_agents),
        "enabled_tools": sorted(policy.enabled_tools) if policy.enabled_tools is not None else None,
        "disabled_tools": sorted(policy.disabled_tools),
        "preferred_tools": list(policy.preferred_tools),
        "suppressed_context_sections": sorted(policy.suppressed_context_sections),
        "enabled_context_sections": sorted(policy.enabled_context_sections),
        "route_override": policy.route_override,
        "tool_schema_policy": policy.tool_schema_policy,
        "context_policy": policy.context_policy,
        "enabled_shortcuts": sorted(policy.enabled_shortcuts),
        "disabled_shortcuts": sorted(policy.disabled_shortcuts),
        "max_turns": policy.max_turns,
        "max_llm_calls": policy.max_llm_calls,
        "max_tool_calls": policy.max_tool_calls,
        "max_prompt_chars": policy.max_prompt_chars,
        "max_skill_chars": policy.max_skill_chars,
        "source_skills": list(policy.source_skills),
        "warnings": list(policy.warnings),
    }


def _clean_list(values) -> list[str]:
    return [str(item).strip() for item in list(values or []) if str(item).strip()]


def _extend_unique(target: list[str], values) -> None:
    seen = set(target)
    for value in _clean_list(values):
        if value in seen:
            continue
        target.append(value)
        seen.add(value)


def _merge_restricted(current: int | None, incoming: int | None) -> int | None:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return min(current, incoming)


def build_execution_policy_from_skills(
    selected_skill_names: list[str],
    registry: SkillRegistry,
    phase: str = "planner",
) -> ExecutionPolicy:
    policy = ExecutionPolicy()
    normalized_phase = normalize_skill_phase(phase)

    for skill_name in _clean_list(selected_skill_names):
        spec = registry.get_skill(skill_name)
        if spec is None:
            policy.warnings.append(f"unknown skill ignored: {skill_name}")
            continue
        if normalized_phase not in [str(item).strip().lower() for item in list(spec.applies_to or [])]:
            policy.warnings.append(
                f"skill ignored for phase mismatch: {skill_name} not allowed in {normalized_phase}"
            )
            continue
        if skill_name not in policy.source_skills:
            policy.source_skills.append(skill_name)

        effects = getattr(spec, "effects", None)
        if effects is None:
            continue

        enable_agents = set(_clean_list(effects.enable_agents))
        if enable_agents:
            if policy.enabled_agents is None:
                policy.enabled_agents = set()
            policy.enabled_agents.update(enable_agents)
        policy.disabled_agents.update(_clean_list(effects.disable_agents))
        _extend_unique(policy.preferred_agents, effects.prefer_agents)

        enable_tools = set(_clean_list(effects.enable_tools))
        if enable_tools:
            if policy.enabled_tools is None:
                policy.enabled_tools = set()
            policy.enabled_tools.update(enable_tools)
        policy.disabled_tools.update(_clean_list(effects.disable_tools))
        _extend_unique(policy.preferred_tools, effects.prefer_tools)

        policy.suppressed_context_sections.update(_clean_list(effects.suppress_context_sections))
        policy.enabled_context_sections.update(_clean_list(effects.enable_context_sections))

        policy.enabled_shortcuts.update(_clean_list(effects.enable_shortcuts))
        policy.disabled_shortcuts.update(_clean_list(effects.disable_shortcuts))

        if effects.route_override:
            if policy.route_override is None:
                policy.route_override = effects.route_override
            elif policy.route_override != effects.route_override:
                policy.warnings.append(
                    f"route_override conflict: kept {policy.route_override}, ignored {effects.route_override} from {skill_name}"
                )

        if effects.tool_schema_policy:
            if policy.tool_schema_policy is None:
                policy.tool_schema_policy = effects.tool_schema_policy
            elif policy.tool_schema_policy != effects.tool_schema_policy:
                policy.warnings.append(
                    f"tool_schema_policy conflict: kept {policy.tool_schema_policy}, ignored {effects.tool_schema_policy} from {skill_name}"
                )

        if effects.context_policy:
            if policy.context_policy is None:
                policy.context_policy = effects.context_policy
            elif policy.context_policy != effects.context_policy:
                policy.warnings.append(
                    f"context_policy conflict: kept {policy.context_policy}, ignored {effects.context_policy} from {skill_name}"
                )

        policy.max_turns = _merge_restricted(policy.max_turns, effects.max_turns)
        policy.max_llm_calls = _merge_restricted(policy.max_llm_calls, effects.max_llm_calls)
        policy.max_tool_calls = _merge_restricted(policy.max_tool_calls, effects.max_tool_calls)
        policy.max_prompt_chars = _merge_restricted(policy.max_prompt_chars, effects.max_prompt_chars)
        policy.max_skill_chars = _merge_restricted(policy.max_skill_chars, effects.max_skill_chars)

    if policy.enabled_agents is not None:
        policy.enabled_agents.difference_update(policy.disabled_agents)
    if policy.enabled_tools is not None:
        policy.enabled_tools.difference_update(policy.disabled_tools)
    policy.enabled_context_sections.difference_update(policy.suppressed_context_sections)
    policy.enabled_shortcuts.difference_update(policy.disabled_shortcuts)

    policy.preferred_agents = [
        name
        for name in policy.preferred_agents
        if name not in policy.disabled_agents and (policy.enabled_agents is None or name in policy.enabled_agents)
    ]
    policy.preferred_tools = [
        name
        for name in policy.preferred_tools
        if name not in policy.disabled_tools and (policy.enabled_tools is None or name in policy.enabled_tools)
    ]

    return policy
