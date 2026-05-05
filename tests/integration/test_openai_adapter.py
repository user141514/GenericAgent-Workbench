"""
Integration tests for OpenAIContextAdapter (Phase M5).

Verifies:
  I6: All injected context blocks have structural markers.
  I1: Adapter output has correct ordering (raw_query LAST).
  I1b: Adapter handles empty/missing blocks gracefully.
  I1c: build_inputs_from_packet works with a ContextPacket.

Phase M5 — adapter validation. No runtime injection is tested here.

Usage:
    pytest tests/integration/test_openai_adapter.py -v
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_MIN_PYTHON = (3, 10)
_py_version = sys.version_info[:2]
CAN_LOAD = _py_version >= _MIN_PYTHON

skip_if_py_too_old = pytest.mark.skipif(
    not CAN_LOAD,
    reason=f"Python {'.'.join(map(str, _MIN_PYTHON))}+ required. Current: {sys.version}",
)


# ═══ Helpers ════════════════════════════════════════════════════════════════

def _count_role_user(inputs):
    """Count entries with role=user."""
    return sum(1 for i in inputs if i.get("role") == "user")


def _all_content(inputs):
    """Return concatenated content of all entries."""
    return "\n".join(str(i.get("content", "")) for i in inputs)


# ═══ I6: Structural markers ═════════════════════════════════════════════════

@skip_if_py_too_old
def test_all_context_blocks_have_markers():
    """I6: Every injected context block (not raw_query) carries a structural marker."""
    from core.context.adapters import OpenAIContextAdapter

    adapter = OpenAIContextAdapter(policy_mode="inject")
    inputs = adapter.build_inputs(
        input_items=[],
        working_memory="### [WORKING MEMORY]\n<history>\n[USER]: test\n</history>",
        context_packet="[CONTEXT PACKET — preview]\n## Workspace\ncwd: /test\n[/CONTEXT PACKET]",
        recent_block="[RECENT CONTEXT]\nTurn 1\n[/RECENT CONTEXT]",
        legacy_memory="[LEGACY PROJECT MEMORY]\nL1 insight here",
        route_hint="[ROUTER HINT] Transfer to code_agent",
        answer_quality="### Answer Quality Guard\nTest quality guard",
        sop_context="[ACTIVE SKILLS]\nSkill: test-skill",
        prefetch_block="[PREFETCH CONTENT]\nFile content preview",
        clarification="[CONTEXT NOTE] Ambiguous follow-up",
        raw_query="Write a test function",
    )

    # The last entry should be the raw query (no marker prefix added by adapter)
    assert inputs[-1]["content"] == "Write a test function"

    # All non-empty context blocks before the last should have markers
    marker_patterns = [
        "[WORKING MEMORY]",
        "[CONTEXT PACKET]",
        "[RECENT CONTEXT]",
        "[PROJECT MEMORY]",
        "[ROUTER HINT]",
        "[ANSWER QUALITY]",
        "[ACTIVE SKILLS]",
        "[PREFETCH CONTENT]",
        "[CONTEXT NOTE]",
    ]

    content = _all_content(inputs[:-1])  # exclude raw_query
    for marker in marker_patterns:
        assert marker in content, f"Marker {marker} not found in assembled context"


@skip_if_py_too_old
def test_raw_query_is_last():
    """Raw user query is always the last entry."""
    from core.context.adapters import OpenAIContextAdapter

    adapter = OpenAIContextAdapter()
    inputs = adapter.build_inputs(
        input_items=[],
        working_memory="wm",
        legacy_memory="lm",
        recent_block="rt",
        raw_query="USER QUERY HERE",
    )

    assert inputs[-1]["role"] == "user"
    assert inputs[-1]["content"] == "USER QUERY HERE"


# ═══ I1b: Graceful empty handling ══════════════════════════════════════════

@skip_if_py_too_old
def test_empty_blocks_are_omitted():
    """Empty or whitespace-only blocks are not added to inputs."""
    from core.context.adapters import OpenAIContextAdapter

    adapter = OpenAIContextAdapter()
    inputs = adapter.build_inputs(
        input_items=[],
        working_memory="",
        context_packet="",
        recent_block="   ",
        legacy_memory="",
        route_hint="",
        answer_quality="",
        sop_context="",
        prefetch_block="",
        clarification="",
        raw_query="only this",
    )

    # Only raw_query should be present (input_items is empty, all blocks empty)
    assert len(inputs) == 1
    assert inputs[0]["content"] == "only this"


@skip_if_py_too_old
def test_partial_blocks():
    """Some blocks filled, some empty — only non-empty appear."""
    from core.context.adapters import OpenAIContextAdapter

    adapter = OpenAIContextAdapter()
    inputs = adapter.build_inputs(
        input_items=[],
        working_memory="[WORKING MEMORY] present",
        context_packet="",
        recent_block="",
        legacy_memory="[PROJECT MEMORY] present",
        route_hint="",
        answer_quality="",
        sop_context="",
        prefetch_block="",
        clarification="",
        raw_query="query",
    )

    content = _all_content(inputs)
    assert "[WORKING MEMORY]" in content
    assert "[PROJECT MEMORY]" in content
    # raw_query comes last
    assert inputs[-1]["content"] == "query"


# ═══ I1c: build_inputs_from_packet ═════════════════════════════════════════

@skip_if_py_too_old
def test_build_inputs_from_packet():
    """build_inputs_from_packet works with a ContextPacket."""
    from core.context.adapters import OpenAIContextAdapter
    from core.context.context_builder import ContextBuilder

    # Create a minimal packet using ContextBuilder
    builder = ContextBuilder(max_chars=2000, policy_mode="preview")

    # Make fake workspace
    class WS:
        cwd = str(PROJECT_ROOT)
        git_root = str(PROJECT_ROOT)
        git_branch = "main"
        has_uncommitted_changes = False
        dirty_files = []

    packet = builder.build(
        workspace=WS(),
        recent_turns_block="[RECENT CONTEXT]\nTurn 1: wrote tests\n[/RECENT CONTEXT]",
        working_memory_block="### [WORKING MEMORY]\n<history>\n[USER]: write tests\n</history>",
        target_route="code",
    )

    adapter = OpenAIContextAdapter(policy_mode="inject")
    inputs = adapter.build_inputs_from_packet(
        input_items=[],
        packet=packet,
        route_hint="[ROUTER HINT] code_agent",
        answer_quality="### Answer Quality\nGuard active",
        raw_query="write a test",
    )

    # Verify structure
    assert len(inputs) > 1  # packet blocks + route-specific + raw_query
    assert inputs[-1]["content"] == "write a test"

    content = _all_content(inputs)
    assert "[ROUTER HINT]" in content
    assert "Answer Quality" in content


# ═══ I1: Ordering ══════════════════════════════════════════════════════════

@skip_if_py_too_old
def test_inputs_preserve_input_items_order():
    """input_items are preserved at the beginning of the list."""
    from core.context.adapters import OpenAIContextAdapter

    existing = [
        {"role": "user", "content": "prior message 1"},
        {"role": "assistant", "content": "prior response 1"},
    ]

    adapter = OpenAIContextAdapter()
    inputs = adapter.build_inputs(
        input_items=existing,
        working_memory="wm",
        raw_query="new query",
    )

    # First two entries should be the input_items
    assert inputs[0] == existing[0]
    assert inputs[1] == existing[1]
    # Last should be raw_query
    assert inputs[-1]["content"] == "new query"


@skip_if_py_too_old
def test_duplicate_marker_not_added():
    """If content already has a marker, don't double-wrap."""
    from core.context.adapters import OpenAIContextAdapter

    adapter = OpenAIContextAdapter()
    inputs = adapter.build_inputs(
        input_items=[],
        working_memory="[WORKING MEMORY]\nAlready marked content",
        raw_query="query",
    )

    content = _all_content(inputs)
    # Should only appear once (not [[WORKING MEMORY]][WORKING MEMORY])
    assert content.count("[WORKING MEMORY]") == 1
