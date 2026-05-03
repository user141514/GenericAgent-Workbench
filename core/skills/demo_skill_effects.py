from __future__ import annotations

from core.runtime.execution_policy import build_execution_policy_from_skills

from .skill_effects import SkillEffects
from .skill_registry import SkillRegistry, SkillSpec


def _demo_spec(
    name: str,
    *,
    applies_to: list[str] | None = None,
    effects: SkillEffects | None = None,
) -> SkillSpec:
    return SkillSpec(
        name=name,
        category="testing",
        description=f"demo spec {name}",
        triggers=[],
        negative_triggers=[],
        source_url="",
        file_path=f"demo://{name}",
        enabled=True,
        applies_to=applies_to or ["planner"],
        effects=effects or SkillEffects(),
    )


def main() -> None:
    registry = SkillRegistry()

    policy_a = build_execution_policy_from_skills(
        ["performance-optimization", "incremental-implementation"],
        registry,
        phase="planner",
    )
    assert policy_a.tool_schema_policy == "slim", policy_a
    assert policy_a.max_turns == 4, policy_a
    assert policy_a.max_prompt_chars == 12000, policy_a
    assert policy_a.suppressed_context_sections == {
        "full_memory_dump",
        "long_history",
        "unrelated_skills",
    }, policy_a
    assert policy_a.source_skills == [
        "performance-optimization",
        "incremental-implementation",
    ], policy_a

    policy_b = build_execution_policy_from_skills(
        ["planning-and-task-breakdown"],
        registry,
        phase="planner",
    )
    assert policy_b.disabled_tools == {"file_write", "file_patch", "shell"}, policy_b
    assert policy_b.context_policy == "read_only_planning", policy_b

    conflict_registry = SkillRegistry(
        specs=[
            _demo_spec("turn-six", effects=SkillEffects(max_turns=6)),
            _demo_spec("turn-three", effects=SkillEffects(max_turns=3)),
            _demo_spec("route-chat", effects=SkillEffects(route_override="chat")),
            _demo_spec("route-executor", effects=SkillEffects(route_override="executor")),
        ]
    )

    policy_c = build_execution_policy_from_skills(
        ["turn-six", "turn-three"],
        conflict_registry,
        phase="planner",
    )
    assert policy_c.max_turns == 3, policy_c

    policy_d = build_execution_policy_from_skills(
        ["route-chat", "route-executor"],
        conflict_registry,
        phase="planner",
    )
    assert policy_d.route_override == "chat", policy_d
    assert any("route_override conflict" in warning for warning in policy_d.warnings), policy_d

    policy_e = build_execution_policy_from_skills([], registry, phase="planner")
    assert policy_e.source_skills == [], policy_e
    assert policy_e.route_override is None, policy_e
    assert policy_e.enabled_agents is None, policy_e
    assert policy_e.disabled_tools == set(), policy_e

    print("demo_skill_effects: OK")


if __name__ == "__main__":
    main()
