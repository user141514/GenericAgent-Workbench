from __future__ import annotations

from .skill_selector import SkillSelector


_PLAN_QUERY = "\u5e2e\u6211\u89c4\u5212\u4e00\u4e0b\u8fd9\u4e2a\u529f\u80fd\u600e\u4e48\u5206\u9636\u6bb5\u5b9e\u73b0"
_VERIFY_QUERY = "\u8fd9\u4e00\u6b65\u600e\u4e48\u9a8c\u8bc1\uff1f"
_PERF_QUERY = "\u8fd0\u884c\u901f\u5ea6\u592a\u6162"
_TEST_QUERY = "\u5199 pytest \u5355\u6d4b"
_DEBUG_QUERY = "\u8fd9\u4e2a\u62a5\u9519\u600e\u4e48\u4fee\uff1f"
_PERF_VERIFY_QUERY = "\u4e0b\u4e00\u6b65\u600e\u4e48\u4f18\u5316\u8fd0\u884c\u901f\u5ea6\u5e76\u9a8c\u8bc1\uff1f"
_DEBUG_SLOW_QUERY = "\u8fd9\u4e2a\u62a5\u9519\u592a\u6162\uff0c\u4e0b\u4e00\u6b65\u600e\u4e48\u5b9a\u4f4d\uff1f"
_REVIEW_QUERY = "\u4ee3\u7801\u5ba1\u67e5\u4e00\u4e0b\u8fd9\u4e2a diff"
_HELLO_QUERY = "\u4f60\u597d"


def _names(selector: SkillSelector, text: str, phase: str = "planner") -> list[str]:
    return selector.select_skills_for_task(text, phase=phase)


def main() -> None:
    selector = SkillSelector()

    planner_perf = selector.select_skill_matches_for_task(
        "\u4e0b\u4e00\u6b65\u600e\u4e48\u4f18\u5316\u8fd0\u884c\u901f\u5ea6\uff1f",
        phase="planner",
    )
    assert [match.name for match in planner_perf] == [
        "performance-optimization",
        "incremental-implementation",
    ], planner_perf
    assert planner_perf[0].score > planner_perf[1].score, planner_perf
    assert planner_perf[0].phase == "planner", planner_perf
    assert "planner" in planner_perf[0].applies_to, planner_perf

    assert _names(selector, _VERIFY_QUERY, phase="planner") == ["test-driven-development"]
    assert _names(selector, _VERIFY_QUERY, phase="reviewer") == []

    assert _names(selector, _PLAN_QUERY, phase="planner") == ["planning-and-task-breakdown"]
    assert _names(selector, _PLAN_QUERY, phase="executor") == []

    executor_debug = selector.select_skill_matches_for_task(_DEBUG_QUERY, phase="executor")
    assert [match.name for match in executor_debug] == ["debugging-and-error-recovery"], executor_debug
    assert executor_debug[0].phase == "executor", executor_debug

    review_categories = selector.select_category_matches_for_task(_REVIEW_QUERY)
    assert review_categories and review_categories[0].category == "review", review_categories
    assert _names(selector, _REVIEW_QUERY, phase="reviewer") == []

    assert _names(selector, _PERF_QUERY, phase="planner") == ["performance-optimization"]
    assert _names(selector, _TEST_QUERY, phase="planner") == ["test-driven-development"]

    perf_verify = selector.select_skill_matches_for_task(_PERF_VERIFY_QUERY, phase="planner")
    assert len(perf_verify) <= 2, perf_verify
    assert perf_verify[0].name == "performance-optimization", perf_verify
    assert perf_verify[1].name in {"test-driven-development", "incremental-implementation"}, perf_verify

    debug_slow = selector.select_skill_matches_for_task(_DEBUG_SLOW_QUERY, phase="planner")
    assert len(debug_slow) <= 2, debug_slow
    assert [match.name for match in debug_slow] == [
        "debugging-and-error-recovery",
        "performance-optimization",
    ], debug_slow

    assert _names(selector, _HELLO_QUERY, phase="planner") == []

    print("demo_skill_selector: OK")


if __name__ == "__main__":
    main()
