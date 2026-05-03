from __future__ import annotations

from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector


def main() -> None:
    registry = SkillRegistry()
    selector = SkillSelector(registry)

    names = [spec.name for spec in registry.list_skills()]

    # ── subset check: expected imported skills must be present ──────────
    expected_imported = {
        "debugging-and-error-recovery",
        "incremental-implementation",
        "performance-optimization",
    }
    assert set(names).issuperset(expected_imported), (
        f"Missing expected skills: {expected_imported - set(names)}"
    )

    # ── selector behaviour ─────────────────────────────────────────────
    assert selector.select_skills_for_task("运行速度太慢，需要 profile 一下") == ["performance-optimization"]
    assert selector.select_skills_for_task("这个报错怎么修，贴了 traceback") == ["debugging-and-error-recovery"]
    assert selector.select_skills_for_task("下一步最小实现，不要大重构") == ["incremental-implementation"]

    # ── each expected skill loads text and resolves spec ───────────────
    for skill_name in expected_imported:
        text = registry.load_skill_text(skill_name)
        spec = registry.get_skill(skill_name)
        assert spec is not None
        assert len(text) <= spec.max_chars

    # ── manifest_only / disabled skills must not appear as enabled imported ──
    for spec in registry.list_skills():
        if spec.import_status in ("manifest_only", "disabled"):
            assert not spec.enabled, (
                f"{spec.name}: {spec.import_status} should not be enabled"
            )
        if spec.enabled and spec.import_status == "imported":
            assert registry.load_skill_text(spec.name), (
                f"{spec.name}: enabled imported but load_skill_text failed"
            )

    print("demo_skill_registry: OK")


if __name__ == "__main__":
    main()
