from __future__ import annotations

from core.skills.skill_prompt_injector import build_optional_sop_context


def test_optional_sop_context_is_compressed_by_default():
    context = build_optional_sop_context("profile latency bottleneck", phase="planner")

    block = context["block"]
    assert context["selected_skills"] == ["performance-optimization"]
    assert context["chars"] <= 1400
    assert "minimal_sop:" in block
    assert "matched_triggers:" in block
    assert "source_url:" not in block
    assert "## Intent" not in block


def test_optional_sop_honors_small_total_budget():
    context = build_optional_sop_context(
        "profile latency bottleneck and pytest verification",
        max_skills=2,
        max_chars_per_skill=400,
        max_total_chars=900,
        phase="planner",
    )

    assert context["chars"] <= 900
    assert context["block"].count("[Skill: ") <= 2
