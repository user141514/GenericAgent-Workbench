from __future__ import annotations

import os

from .skill_prompt_injector import (
    SKILL_SOP_ENV_VAR,
    build_optional_sop_block,
    build_optional_sop_context,
    skill_sop_enabled,
)


_PERF_QUERY = "\u8fd0\u884c\u901f\u5ea6\u592a\u6162\uff0c\u9700\u8981\u5148\u505a profile \u548c latency \u5206\u6790"
_INCR_QUERY = "\u4e0b\u4e00\u6b65\u6700\u5c0f\u5b9e\u73b0\uff0c\u4e0d\u8981\u5927\u91cd\u6784"
_PLAN_QUERY = "\u5e2e\u6211\u89c4\u5212\u4e00\u4e0b\u8fd9\u4e2a\u529f\u80fd\u600e\u4e48\u5206\u9636\u6bb5\u5b9e\u73b0"
_VERIFY_QUERY = "\u8fd9\u4e00\u6b65\u600e\u4e48\u9a8c\u8bc1\uff1f"
_HELLO_QUERY = "\u4f60\u597d\uff0c\u4eca\u5929\u5929\u6c14\u600e\u4e48\u6837"
_MIXED_QUERY = "\u4e0b\u4e00\u6b65\u600e\u4e48\u4f18\u5316\u8fd0\u884c\u901f\u5ea6\uff1f"
_LIMITED_QUERY = "\u4e0b\u4e00\u6b65\u600e\u4e48\u4f18\u5316\u8fd0\u884c\u901f\u5ea6\u5e76\u9a8c\u8bc1\uff1f"


def main() -> None:
    os.environ[SKILL_SOP_ENV_VAR] = "0"
    assert not skill_sop_enabled()

    perf_block = build_optional_sop_block(_PERF_QUERY, phase="planner")
    assert perf_block.startswith("### Optional SOP"), perf_block
    assert "[Skill: performance-optimization]" in perf_block, perf_block
    assert len(perf_block) <= 3500, len(perf_block)

    incr_block = build_optional_sop_block(_INCR_QUERY, phase="planner")
    assert "[Skill: incremental-implementation]" in incr_block, incr_block
    assert len(incr_block) <= 3500, len(incr_block)

    planning_block = build_optional_sop_block(_PLAN_QUERY, phase="planner")
    assert "[Skill: planning-and-task-breakdown]" in planning_block, planning_block
    assert len(planning_block) <= 3500, len(planning_block)

    testing_block = build_optional_sop_block(_VERIFY_QUERY, phase="planner")
    assert "[Skill: test-driven-development]" in testing_block, testing_block
    assert len(testing_block) <= 3500, len(testing_block)

    reviewer_block = build_optional_sop_block(_VERIFY_QUERY, phase="reviewer")
    assert reviewer_block == "", reviewer_block

    greeting_block = build_optional_sop_block(_HELLO_QUERY, phase="planner")
    assert greeting_block == "", greeting_block

    mixed_context = build_optional_sop_context(_MIXED_QUERY, phase="planner")
    assert mixed_context["phase"] == "planner", mixed_context
    assert mixed_context["selected_skills"] == [
        "performance-optimization",
        "incremental-implementation",
    ], mixed_context
    assert len(mixed_context["skill_matches"]) == 2, mixed_context
    assert mixed_context["skill_matches"][0]["name"] == "performance-optimization", mixed_context
    assert mixed_context["skill_matches"][0]["phase"] == "planner", mixed_context
    assert "planner" in mixed_context["skill_matches"][0]["applies_to"], mixed_context
    assert mixed_context["chars"] <= 3500, mixed_context

    verify_context = build_optional_sop_context(_VERIFY_QUERY, phase="planner")
    assert verify_context["selected_skills"] == ["test-driven-development"], verify_context
    assert verify_context["skill_matches"][0]["name"] == "test-driven-development", verify_context
    assert verify_context["chars"] <= 3500, verify_context

    reviewer_context = build_optional_sop_context(_VERIFY_QUERY, phase="reviewer")
    assert reviewer_context["selected_skills"] == [], reviewer_context
    assert reviewer_context["phase"] == "reviewer", reviewer_context

    limited_context = build_optional_sop_context(
        _LIMITED_QUERY,
        max_skills=1,
        max_total_chars=2000,
        phase="planner",
    )
    limited_block = limited_context["block"]
    assert limited_block.count("[Skill: ") == 1, limited_block
    assert len(limited_block) <= 2000, len(limited_block)
    assert len(limited_context["selected_skills"]) == 1, limited_context
    assert len(limited_context["skill_matches"]) == 1, limited_context

    os.environ[SKILL_SOP_ENV_VAR] = "1"
    assert skill_sop_enabled()
    enabled_context = build_optional_sop_context(_PERF_QUERY, phase="planner")
    assert enabled_context["chars"] <= 3500, enabled_context
    assert enabled_context["skill_matches"][0]["name"] == "performance-optimization", enabled_context

    print("demo_skill_prompt_injector: OK")


if __name__ == "__main__":
    main()
