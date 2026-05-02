from __future__ import annotations

from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector


def main() -> None:
    registry = SkillRegistry()
    selector = SkillSelector(registry)

    names = [spec.name for spec in registry.list_skills()]
    assert names == [
        "debugging-and-error-recovery",
        "incremental-implementation",
        "performance-optimization",
    ], names

    assert selector.select_skills_for_task("运行速度太慢，需要 profile 一下") == ["performance-optimization"]
    assert selector.select_skills_for_task("这个报错怎么修，贴了 traceback") == ["debugging-and-error-recovery"]
    assert selector.select_skills_for_task("下一步最小实现，不要大重构") == ["incremental-implementation"]

    for skill_name in names:
        text = registry.load_skill_text(skill_name)
        spec = registry.get_skill(skill_name)
        assert spec is not None
        assert len(text) <= spec.max_chars

    print("demo_skill_registry: OK")


if __name__ == "__main__":
    main()
