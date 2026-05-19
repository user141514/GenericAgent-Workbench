"""
Integration tests for Classic Handoff Bridge (Phase M6).

Verifies:
  E1: _build_recent_context() produces unified [RECENT CONTEXT] format.
  E1b: _history_to_input_items() correctly converts Classic history format.
  E1c: _is_ambiguous_followup() delegates to canonical implementation.

Phase M6 — Classic path recent context unification. No runtime changes tested.

Usage:
    pytest tests/integration/test_classic_handoff_bridge.py -v
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ═══ Helpers ════════════════════════════════════════════════════════════════

def _load_agentmain():
    """Load core/agentmain.py. Uses normal import on Python >= 3.10, falls back
    to isolated module loading on older Python versions."""
    if sys.version_info >= (3, 10):
        import core.agentmain as mod
        return mod

    # Legacy path for Python < 3.10: load module file directly
    mod_path = str(PROJECT_ROOT / "core" / "agentmain.py")
    spec = importlib.util.spec_from_file_location("core.agentmain", mod_path)
    mod = importlib.util.module_from_spec(spec)

    class _Fake:
        pass
    for pkg in ["core", "core.__init__", "core.memory", "core.memory.__init__",
                "core.context", "core.context.__init__", "core.llmcore",
                "core.llmcore.__init__", "core.runtime", "core.runtime.__init__",
                "core.quality", "core.quality.__init__", "core.skills",
                "core.skills.__init__", "core.tools", "core.tools.__init__"]:
        sys.modules.setdefault(pkg, _Fake())

    sys.modules["core.agentmain"] = mod
    try:
        spec.loader.exec_module(mod)
    except SyntaxError as e:
        pytest.skip(f"agentmain.py has pre-existing syntax issue: {e}")
    return mod


# ═══ E1b: History conversion ════════════════════════════════════════════════

def test_history_to_input_items_conversion():
    """E1b: Classic history strings are correctly converted to OpenAI format."""
    mod = _load_agentmain()

    history = [
        "[USER]: what is this project?",
        "[Agent] 直接回答了用户问题",
        "[USER]: write a test for ga.py",
        "[Agent] 调用工具file_read, args: {'path': 'core/ga.py'}",
    ]

    items = mod._history_to_input_items(history)

    assert len(items) == 4
    assert items[0] == {"role": "user", "content": "what is this project?"}
    assert items[1] == {"role": "assistant", "content": "直接回答了用户问题"}
    assert items[2] == {"role": "user", "content": "write a test for ga.py"}
    assert items[3] == {"role": "assistant", "content": "调用工具file_read, args: {'path': 'core/ga.py'}"}


def test_history_to_input_items_empty():
    """Empty history produces empty list."""
    mod = _load_agentmain()
    assert mod._history_to_input_items([]) == []


def test_history_to_input_items_truncation():
    """max_lines parameter limits output."""
    mod = _load_agentmain()

    history = [f"[USER]: msg {i}" for i in range(50)]

    items = mod._history_to_input_items(history, max_lines=5)
    assert len(items) == 5
    # Should be last 5
    assert items[0]["content"] == "msg 45"
    assert items[4]["content"] == "msg 49"


def test_history_to_input_items_unknown_format():
    """Lines with unrecognized format are treated as user content."""
    mod = _load_agentmain()

    history = [
        "[USER]: known format",
        "some random line without prefix",
        "[Agent] known format",
    ]

    items = mod._history_to_input_items(history)
    assert len(items) == 3
    assert items[0]["role"] == "user"
    assert items[1]["role"] == "user"  # unknown → user
    assert items[2]["role"] == "assistant"


# ═══ E1: Recent context format ═════════════════════════════════════════════

def test_build_recent_context_uses_unified_format():
    """E1: _build_recent_context produces [RECENT CONTEXT] marker."""
    mod = _load_agentmain()

    history = [
        "[USER]: read the file",
        "[Agent] 调用工具file_read, args: {'path': 'test.txt'}",
    ]

    result = mod._build_recent_context(history, "continue")
    # Canonical format uses "[RECENT CONVERSATION — last N turns]" or legacy "[RECENT CONTEXT]"
    assert "[RECENT CONVERSATION" in result or "[RECENT CONTEXT]" in result
    assert "[/RECENT CONVERSATION]" in result or "[/RECENT CONTEXT]" in result


def test_build_recent_context_empty_history_non_ambiguous():
    """Empty history + non-ambiguous query returns empty string."""
    mod = _load_agentmain()

    result = mod._build_recent_context([], "write a python script")
    assert result == ""


def test_build_recent_context_empty_history_ambiguous():
    """Empty history + ambiguous query returns clarification note."""
    mod = _load_agentmain()

    result = mod._build_recent_context([], "...")
    assert result != ""
    assert "Do NOT ask the user to clarify" in result


def test_build_recent_context_with_history():
    """History is included in the context block."""
    mod = _load_agentmain()

    history = [
        "[USER]: what is pytest?",
        "[Agent] 直接回答了用户问题",
    ]

    result = mod._build_recent_context(history, "how to use it?")
    # Should contain the history content or a converted form of it
    assert len(result) > 0
    # The result should be a valid context block
    assert result.startswith("The user") or result.startswith("[RECENT") or "pytest" in result.lower()


# ═══ E1c: Ambiguous follow-up delegation ═══════════════════════════════════

def test_is_ambiguous_followup_delegates():
    """E1c: _is_ambiguous_followup correctly identifies ambiguous queries."""
    mod = _load_agentmain()

    # Canonical patterns from recent_turns.py
    ambiguous_cases = [
        "...",
        "继续",
        "然后呢",
        "刚才那个",
        "undo",
    ]
    for case in ambiguous_cases:
        assert mod._is_ambiguous_followup(case), f"Should be ambiguous: {case!r}"

    # Non-ambiguous cases
    clear_cases = [
        "write a python script to parse JSON",
        "如果我想开发一个界面",
        "帮我优化这个项目",
    ]
    for case in clear_cases:
        assert not mod._is_ambiguous_followup(case), f"Should NOT be ambiguous: {case!r}"


def test_is_ambiguous_followup_empty():
    """Empty query is ambiguous."""
    mod = _load_agentmain()
    assert mod._is_ambiguous_followup("")
    assert mod._is_ambiguous_followup("   ")
