from __future__ import annotations

from .skill_manifest import SkillManifest
from .skill_selector import SkillSelector


_PERF_QUERY = "\u4e0b\u4e00\u6b65\u600e\u4e48\u4f18\u5316\u8fd0\u884c\u901f\u5ea6\uff1f"
_PLAN_QUERY = "\u5e2e\u6211\u89c4\u5212\u4e00\u4e0b\u8fd9\u4e2a\u529f\u80fd\u600e\u4e48\u5206\u9636\u6bb5\u5b9e\u73b0"
_VERIFY_QUERY = "\u8fd9\u4e00\u6b65\u600e\u4e48\u9a8c\u8bc1\uff1f"
_TEST_QUERY = "\u5199 pytest \u5355\u6d4b"
_SECURITY_QUERY = "\u5b89\u5168\u6f0f\u6d1e\u600e\u4e48\u68c0\u67e5"
_REVIEW_QUERY = "\u4ee3\u7801\u5ba1\u67e5\u4e00\u4e0b\u8fd9\u4e2a diff"
_HELLO_QUERY = "\u4f60\u597d"


def main() -> None:
    manifest = SkillManifest()
    errors = manifest.validate()
    assert errors == [], errors

    all_entries = manifest.list_all()
    imported_entries = manifest.list_imported_enabled()
    imported_names = [item["name"] for item in imported_entries]

    assert len(all_entries) > 5, len(all_entries)
    assert imported_names == [
        "performance-optimization",
        "debugging-and-error-recovery",
        "incremental-implementation",
        "planning-and-task-breakdown",
        "test-driven-development",
    ], imported_names

    selector = SkillSelector()
    assert selector.select_skills_for_task(_PERF_QUERY, phase="planner") == [
        "performance-optimization",
        "incremental-implementation",
    ]
    assert selector.select_skills_for_task(_PLAN_QUERY, phase="planner") == [
        "planning-and-task-breakdown",
    ]
    assert selector.select_skills_for_task(_VERIFY_QUERY, phase="planner") == [
        "test-driven-development",
    ]
    assert selector.select_skills_for_task(_VERIFY_QUERY, phase="reviewer") == []
    assert selector.select_skills_for_task(_TEST_QUERY, phase="planner") == [
        "test-driven-development",
    ]

    testing_categories = selector.select_category_matches_for_task(_TEST_QUERY)
    assert testing_categories and testing_categories[0].category == "testing", testing_categories

    security_categories = selector.select_category_matches_for_task(_SECURITY_QUERY)
    assert security_categories and security_categories[0].category == "security", security_categories
    assert selector.select_skills_for_task(_SECURITY_QUERY, phase="planner") == []

    review_categories = selector.select_category_matches_for_task(_REVIEW_QUERY)
    assert review_categories and review_categories[0].category == "review", review_categories
    assert selector.select_skills_for_task(_REVIEW_QUERY, phase="reviewer") == []

    assert selector.select_skills_for_task(_HELLO_QUERY, phase="planner") == []

    print("demo_skill_manifest: OK")


if __name__ == "__main__":
    main()
