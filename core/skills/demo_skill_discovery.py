from __future__ import annotations

import tempfile
from pathlib import Path

from .skill_discovery import SkillDiscovery, to_manifest_entry
from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        agentskill = root / ".agents" / "skills" / "sample-skill" / "SKILL.md"
        legacy = root / ".agents" / "skills" / "legacy-example.md"

        _write(
            agentskill,
            """---
name: sample-skill
description: Sample project skill for smoke discovery.
triggers:
  - custom smoke
  - sample flow
category: testing
applies_to:
  - planner
  - verifier
enabled: true
max_chars: 1700
---

# Sample Skill

Use this for sample discovery only.
""",
        )
        _write(
            legacy,
            """# legacy-example

Legacy project skill placeholder.
""",
        )

        discovery = SkillDiscovery(work_dir=root)
        skills = discovery.discover()
        names = {item.name for item in skills}
        assert "sample-skill" in names, names
        assert "legacy-example" in names, names

        sample = next(item for item in skills if item.name == "sample-skill")
        legacy_item = next(item for item in skills if item.name == "legacy-example")
        assert sample.format == "agentskills", sample
        assert legacy_item.format == "legacy", legacy_item
        assert sample.source_scope == "project", sample
        assert legacy_item.source_scope == "project", legacy_item
        assert sample.enabled is False, sample
        assert legacy_item.enabled is False, legacy_item
        assert sample.import_status == "discovered", sample
        assert sample.risk_level == "medium", sample

        manifest_entry = to_manifest_entry(sample)
        assert manifest_entry["name"] == "sample-skill", manifest_entry
        assert manifest_entry["enabled"] is False, manifest_entry
        assert manifest_entry["import_status"] == "discovered", manifest_entry
        assert manifest_entry["local_file"].endswith("SKILL.md"), manifest_entry

        registry = SkillRegistry(include_discovered=True, work_dir=root)
        discovered = registry.list_discovered_skills()
        discovered_names = {item.name for item in discovered}
        assert "sample-skill" in discovered_names, discovered_names
        assert "legacy-example" in discovered_names, discovered_names

        selector = SkillSelector()
        assert selector.select_skills_for_task("custom smoke") == []

        print("demo_skill_discovery: OK")


if __name__ == "__main__":
    main()
