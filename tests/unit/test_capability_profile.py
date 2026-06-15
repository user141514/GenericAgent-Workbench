"""Unit tests for core.agents.capability_profile."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.agents.capability_profile import (
    CapabilityProfile,
    ProfileManager,
    _parse_frontmatter,
    build_agent_instructions,
    load_profile_from_md,
    profile_dir,
)


class TestFrontmatterParsing:
    def test_empty_yields_empty(self):
        fm, body = _parse_frontmatter("just plain text")
        assert fm == {}
        assert body == "just plain text"

    def test_no_delimiter(self):
        fm, body = _parse_frontmatter("# Heading\n\nContent here")
        assert fm == {}
        assert body == "# Heading\n\nContent here"

    def test_simple_frontmatter(self):
        text = """---
name: test-agent
description: Does testing
tools: [file_read, grep]
max_turns: 5
---
Body content."""
        fm, body = _parse_frontmatter(text)
        assert fm["name"] == "test-agent"
        assert fm["description"] == "Does testing"
        assert fm["tools"] == ["file_read", "grep"]
        assert fm["max_turns"] == 5
        assert body == "Body content."

    def test_boolean_values(self):
        text = """---
enabled: true
verbose: false
---
ok"""
        fm, _ = _parse_frontmatter(text)
        assert fm["enabled"] is True
        assert fm["verbose"] is False

    def test_null_values(self):
        text = """---
model: null
other: ~
third:
---
By itself."""
        fm, _ = _parse_frontmatter(text)
        assert fm["model"] is None
        assert fm["other"] is None
        assert fm["third"] is None


class TestBuildAgentInstructions:
    def test_no_persona_language(self):
        """The output must NEVER contain role-playing language."""
        profile = CapabilityProfile(
            name="test-agent",
            description="Runs tests and reports results",
        )
        instructions = build_agent_instructions(profile)
        # Must NOT contain persona language
        forbidden = [
            "you are a senior",
            "you are an expert",
            "you are a skilled",
            "you are a world-class",
            "you are an experienced",
            "as a developer",
            "with years of",
        ]
        lowered = instructions.lower()
        for phrase in forbidden:
            assert phrase not in lowered, f"Found persona language: {phrase!r}"

    def test_contains_capability_header(self):
        profile = CapabilityProfile(name="test-agent", description="Does stuff")
        instructions = build_agent_instructions(profile)
        assert "## CAPABILITY: test-agent" in instructions
        assert "Does stuff" in instructions

    def test_lists_allowed_tools(self):
        profile = CapabilityProfile(
            name="reader",
            description="Reads code",
            tools=["file_read", "grep", "glob"],
        )
        instructions = build_agent_instructions(profile)
        assert "### ALLOWED TOOLS" in instructions
        assert "`file_read`" in instructions
        assert "`grep`" in instructions
        assert "`glob`" in instructions

    def test_lists_restricted_tools(self):
        profile = CapabilityProfile(
            name="reader",
            description="Reads code",
            disallowed_tools=["file_write", "code_run"],
        )
        instructions = build_agent_instructions(profile)
        assert "### RESTRICTED TOOLS" in instructions
        assert "`file_write`" in instructions
        assert "`code_run`" in instructions
        assert "(blocked)" in instructions

    def test_constraints_section(self):
        profile = CapabilityProfile(
            name="limited",
            description="Limited agent",
            max_turns=5,
            effort="high",
            context_policy="read_only",
        )
        instructions = build_agent_instructions(profile)
        assert "### CONSTRAINTS" in instructions
        assert "Maximum turns: 5" in instructions
        assert "read_only" in instructions
        assert "high" in instructions

    def test_identity_is_capability_based(self):
        profile = CapabilityProfile(name="worker", description="Does work")
        instructions = build_agent_instructions(profile)
        assert "### IDENTITY" in instructions
        assert "tool-use kernel" in instructions.lower()
        assert "capabilities and constraints" in instructions.lower()

    def test_no_allowed_tools_when_empty(self):
        profile = CapabilityProfile(name="full-access", description="Has all tools")
        instructions = build_agent_instructions(profile)
        assert "### ALLOWED TOOLS" not in instructions

    def test_no_restricted_tools_when_empty(self):
        profile = CapabilityProfile(name="full-access", description="Has all tools")
        instructions = build_agent_instructions(profile)
        assert "### RESTRICTED TOOLS" not in instructions

    def test_lists_skills(self):
        profile = CapabilityProfile(
            name="skilled",
            description="Skilled agent",
            skills=["tdd", "code-review"],
        )
        instructions = build_agent_instructions(profile)
        assert "### LOADED SKILLS" in instructions
        assert "tdd" in instructions
        assert "code-review" in instructions


class TestLoadProfileFromMd:
    def test_loads_real_example(self):
        """Integration: load the bundled agent .md files."""
        agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
        for name in ("default", "code-reviewer", "researcher"):
            md_path = agents_dir / f"{name}.md"
            if md_path.is_file():
                profile = load_profile_from_md(md_path)
                assert profile is not None
                assert profile.name == name
                assert profile.description

    def test_returns_none_for_missing_file(self):
        result = load_profile_from_md("/nonexistent/path.md")
        assert result is None

    def test_returns_none_for_empty_file(self):
        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("")
            tmp_path = f.name
        try:
            result = load_profile_from_md(tmp_path)
            assert result is None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_falls_back_to_filename(self):
        """When frontmatter has no name, use filename stem."""
        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("---\ndescription: A test profile\ntools: [grep]\n---\nBody")
            tmp_path = f.name
        try:
            profile = load_profile_from_md(tmp_path)
            assert profile is not None
            assert profile.name  # filename stem, non-empty
            assert profile.description == "A test profile"
            assert profile.tools == ["grep"]
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestProfileManager:
    def test_list_profiles_from_bundled_dir(self):
        """Load profiles from the bundled agents/ directory."""
        agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
        manager = ProfileManager(agents_dir)
        profiles = manager.list_profiles()
        assert len(profiles) >= 3
        names = {p.name for p in profiles}
        assert "default" in names
        assert "code-reviewer" in names
        assert "researcher" in names

    def test_get_profile_by_name(self):
        agents_dir = Path(__file__).resolve().parent.parent.parent / "agents"
        manager = ProfileManager(agents_dir)
        profile = manager.get_profile("code-reviewer")
        assert profile is not None
        assert "read_only" in profile.context_policy.lower()
        assert "file_write" in profile.disallowed_tools

    def test_get_nonexistent_profile(self):
        manager = ProfileManager()
        assert manager.get_profile("nonexistent-12345") is None


class TestCapabilityProfileDataclass:
    def test_defaults(self):
        p = CapabilityProfile(name="test", description="Test")
        assert p.tools == []
        assert p.disallowed_tools == []
        assert p.max_turns == 40
        assert p.skills == []
        assert p.model is None
        assert p.effort == "medium"
        assert p.context_policy == "full"
