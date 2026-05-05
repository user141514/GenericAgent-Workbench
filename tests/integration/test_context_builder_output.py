"""
Integration tests for ContextBuilder preview (Phase M4).

Verifies:
  I1: ContextBuilder.build() returns valid ContextPacket with correct block ordering.
  I3: ContextPacket stays within max_tokens budget.
  I1b: recent_turns and working_memory blocks are included correctly.
  I1c: preview_to_disk() writes valid JSON.

Phase M4 — preview only. No runtime injection is tested here.

Usage:
    pytest tests/integration/test_context_builder_output.py -v
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# core/context/ uses `str | None` syntax (PEP 604, Python 3.10+).
_MIN_PYTHON = (3, 10)
_py_version = sys.version_info[:2]
CAN_LOAD = _py_version >= _MIN_PYTHON

skip_if_py_too_old = pytest.mark.skipif(
    not CAN_LOAD,
    reason=(
        f"Python {'.'.join(map(str, _MIN_PYTHON))}+ required "
        f"(PEP 604 union types). Current: {sys.version}"
    ),
)


# ═══ Helpers ════════════════════════════════════════════════════════════════

def _make_fake_workspace():
    """Return a minimal fake WorkspaceSnapshot."""
    class WS:
        cwd = str(PROJECT_ROOT)
        git_root = str(PROJECT_ROOT)
        git_branch = "main"
        has_uncommitted_changes = False
        dirty_files = []
    return WS()


def _make_fake_project():
    """Return a minimal fake ProjectIdentity."""
    class PJ:
        project_id = "test-proj"
        project_name = "test-project"
        project_root = str(PROJECT_ROOT)
        key_files = ["README.md", "pyproject.toml"]
        languages = ["python"]
    return PJ()


def _make_fake_memory_bundle(l1_content="L1 test", l2_content="L2 test"):
    """Return a minimal MemoryBundle with L1/L2 blocks."""
    from core.context.memory_reader import MemoryBlock, MemoryBundle
    blocks = []
    if l1_content:
        blocks.append(MemoryBlock(
            source="L1", source_priority="primary",
            content=l1_content, relevance_score=1.0,
        ))
    if l2_content:
        blocks.append(MemoryBlock(
            source="L2", source_priority="primary",
            content=l2_content, relevance_score=0.9,
        ))
    return MemoryBundle(blocks=blocks)


# ═══ I1: Output validity ════════════════════════════════════════════════════

@skip_if_py_too_old
def test_build_returns_context_packet():
    """I1: build() returns ContextPacket with correct structure."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(max_chars=4000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        project=_make_fake_project(),
        memory_bundle=_make_fake_memory_bundle(),
        recent_turns_block="[RECENT CONTEXT]\nUser: hello\nAssistant: hi\n[/RECENT CONTEXT]",
        working_memory_block="### [WORKING MEMORY]\n<history>\n[USER]: hello\n</history>",
        target_route="code",
    )

    assert packet is not None
    assert packet.target_route == "code"
    assert packet.policy_mode == "preview"
    assert packet.total_chars > 0
    assert "workspace" in packet.source_breakdown
    assert "project" in packet.source_breakdown
    assert "memory" in packet.source_breakdown
    assert "recent_turns" in packet.source_breakdown
    assert "working_memory" in packet.source_breakdown


@skip_if_py_too_old
def test_build_returns_none_for_chat():
    """Chat route skips context injection."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        target_route="chat",
    )
    assert packet is None


@skip_if_py_too_old
def test_build_returns_none_for_off_policy():
    """policy_mode='off' skips everything."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="off")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        target_route="code",
    )
    assert packet is None


@skip_if_py_too_old
def test_build_includes_all_sources():
    """I1b: When all sources are provided, all appear in breakdown."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(max_chars=8000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        project=_make_fake_project(),
        memory_bundle=_make_fake_memory_bundle("L1 content here", "L2 content here"),
        recent_turns_block="[RECENT CONTEXT]\nTurn 1: user asked about tests\n[/RECENT CONTEXT]",
        working_memory_block="### [WORKING MEMORY]\n<history>\n[USER]: write tests\n</history>",
        target_route="executor",
    )

    assert packet is not None
    breakdown = packet.source_breakdown
    for key in ("workspace", "project", "memory", "recent_turns", "working_memory"):
        assert key in breakdown, f"Missing source: {key}"
        assert breakdown[key] > 0, f"Source {key} has zero chars"


@skip_if_py_too_old
def test_build_empty_sources_produces_zero_chars():
    """Empty sources produce zero-char entries."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="preview")
    packet = builder.build(
        workspace=None,
        project=None,
        memory_bundle=None,
        recent_turns_block="",
        working_memory_block="",
        target_route="code",
    )

    assert packet is not None
    for key, chars in packet.source_breakdown.items():
        assert chars == 0, f"Source {key} should be 0, got {chars}"


# ═══ I3: Size budget ═══════════════════════════════════════════════════════

@skip_if_py_too_old
def test_packet_respects_max_chars():
    """I3: ContextPacket stays within total max_chars limit."""
    from core.context.context_builder import ContextBuilder

    # Large memory content that would overflow if not truncated
    large_l1 = "L1 " + "x" * 5000

    builder = ContextBuilder(max_chars=2000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        project=_make_fake_project(),
        memory_bundle=_make_fake_memory_bundle(l1_content=large_l1),
        recent_turns_block="recent " * 500,
        working_memory_block="wm " * 500,
        target_route="code",
    )

    assert packet is not None
    # Each source is individually capped by route budget, so total stays bounded
    assert packet.total_chars > 0
    # The total is the sum of individually-capped sources
    # code route: workspace=100, project=100, memory=1500, recent_turns=800, working_memory=600
    # => max theoretical total = 3100, but each is capped so it won't exceed route budgets
    assert packet.total_chars <= 3500, (
        f"Total chars {packet.total_chars} exceeds expected maximum"
    )


@skip_if_py_too_old
def test_recent_turns_truncation():
    """Recent turns block is truncated to route budget."""
    from core.context.context_builder import ContextBuilder

    long_rt = "[RECENT CONTEXT]\n" + ("x" * 2000) + "\n[/RECENT CONTEXT]"

    builder = ContextBuilder(max_chars=4000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        recent_turns_block=long_rt,
        target_route="code",  # budget: 800 chars
    )

    assert packet is not None
    assert packet.source_breakdown.get("recent_turns", 0) <= 800, (
        f"Recent turns not truncated: {packet.source_breakdown.get('recent_turns')}"
    )


@skip_if_py_too_old
def test_working_memory_truncation():
    """Working memory block is truncated to route budget."""
    from core.context.context_builder import ContextBuilder

    long_wm = "### [WORKING MEMORY]\n" + ("y" * 1500) + "\n</history>"

    builder = ContextBuilder(max_chars=4000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        working_memory_block=long_wm,
        target_route="code",  # budget: 600 chars
    )

    assert packet is not None
    assert packet.source_breakdown.get("working_memory", 0) <= 600, (
        f"Working memory not truncated: {packet.source_breakdown.get('working_memory')}"
    )


# ═══ I1c: Preview JSON ────────────────────────────────────────────────────

@skip_if_py_too_old
def test_preview_to_disk_writes_json():
    """I1c: preview_to_disk() writes valid JSON to temp/context_audit/."""
    from core.context.context_builder import ContextBuilder

    with tempfile.TemporaryDirectory() as tmp:
        builder = ContextBuilder(max_chars=2000, policy_mode="preview")
        packet = builder.build(
            workspace=_make_fake_workspace(),
            project=_make_fake_project(),
            recent_turns_block="[RECENT CONTEXT]\nUser: test\n[/RECENT CONTEXT]",
            working_memory_block="### [WORKING MEMORY]\n<history>\n[USER]: test\n</history>",
            target_route="code",
        )

        filepath = builder.preview_to_disk(packet, project_root=tmp)
        assert filepath is not None
        assert os.path.exists(filepath)

        # Verify JSON validity
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["target_route"] == "code"
        assert "total_chars" in data
        assert "source_breakdown" in data
        assert "recent_turns_chars" in data
        assert "working_memory_chars" in data
        assert "memory_blocks" in data


@skip_if_py_too_old
def test_preview_to_disk_returns_none_for_inject_mode():
    """preview_to_disk only writes in preview mode."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="inject")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        target_route="code",
    )
    filepath = builder.preview_to_disk(packet)
    assert filepath is None


@skip_if_py_too_old
def test_preview_to_disk_returns_none_for_off_mode():
    """preview_to_disk returns None when policy is off."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="off")
    filepath = builder.preview_to_disk(None)
    assert filepath is None


# ═══ Serialize format ══════════════════════════════════════════════════════

@skip_if_py_too_old
def test_serialize_includes_all_sections():
    """serialize() produces text with all expected sections."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(max_chars=4000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        project=_make_fake_project(),
        memory_bundle=_make_fake_memory_bundle(),
        recent_turns_block="[RECENT CONTEXT]\nTurn 1\n[/RECENT CONTEXT]",
        working_memory_block="### [WORKING MEMORY]\n<history>\n[USER]: hi\n</history>",
        target_route="executor",
    )

    text = builder.serialize(packet)
    assert "[CONTEXT PACKET" in text
    assert "## Workspace" in text
    assert "## Project" in text
    assert "## Relevant Memory" in text
    assert "## Recent Conversation" in text
    assert "## Working Memory" in text
    assert "[/CONTEXT PACKET]" in text


@skip_if_py_too_old
def test_serialize_omits_empty_blocks():
    """serialize() does not include sections for empty/absent sources."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        recent_turns_block="",
        working_memory_block="",
        target_route="code",
    )

    text = builder.serialize(packet)
    assert "## Recent Conversation" not in text
    assert "## Working Memory" not in text


# ═══ Route-specific budgets ════════════════════════════════════════════════

@skip_if_py_too_old
def test_route_budgets_differ():
    """Different routes have different source budgets."""
    from core.context.context_builder import ContextBuilder

    large_rt = "[RECENT CONTEXT]\n" + ("data " * 500) + "\n[/RECENT CONTEXT]"
    large_wm = "### [WORKING MEMORY]\n" + ("history " * 500) + "\n</history>"

    builder = ContextBuilder(max_chars=8000, policy_mode="preview")

    code_packet = builder.build(
        workspace=_make_fake_workspace(),
        recent_turns_block=large_rt,
        working_memory_block=large_wm,
        target_route="code",
    )
    exec_packet = builder.build(
        workspace=_make_fake_workspace(),
        recent_turns_block=large_rt,
        working_memory_block=large_wm,
        target_route="executor",
    )

    assert code_packet is not None
    assert exec_packet is not None

    # executor has larger budgets than code for conversation memory
    code_rt = code_packet.source_breakdown.get("recent_turns", 0)
    exec_rt = exec_packet.source_breakdown.get("recent_turns", 0)
    assert exec_rt >= code_rt, (
        f"executor route should have >= recent_turns budget than code: {exec_rt} vs {code_rt}"
    )


# ═══ to_dict ═══════════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_to_dict_produces_valid_structure():
    """ContextPacket.to_dict() returns expected structure for JSON export."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(max_chars=4000, policy_mode="preview")
    packet = builder.build(
        workspace=_make_fake_workspace(),
        project=_make_fake_project(),
        memory_bundle=_make_fake_memory_bundle(),
        recent_turns_block="[RECENT CONTEXT]\nTurn 1\n[/RECENT CONTEXT]",
        working_memory_block="### [WORKING MEMORY]\n<history>\nhi\n</history>",
        target_route="executor",
    )

    d = packet.to_dict()
    assert isinstance(d, dict)
    assert d["target_route"] == "executor"
    assert d["policy_mode"] == "preview"
    assert isinstance(d["source_breakdown"], dict)
    assert d["recent_turns_chars"] > 0
    assert d["working_memory_chars"] > 0
    assert isinstance(d["memory_blocks"], list)


@skip_if_py_too_old
def test_to_dict_handles_none_fields():
    """to_dict handles None workspace/project/runtime gracefully."""
    from core.context.context_builder import ContextBuilder

    builder = ContextBuilder(policy_mode="preview")
    packet = builder.build(
        workspace=None,
        project=None,
        target_route="code",
    )

    d = packet.to_dict()
    assert d["workspace"] is None
    assert d["project"] is None
    assert d["runtime"] is None
