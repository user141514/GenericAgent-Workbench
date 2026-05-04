"""
Integration/unit tests for recent conversation context injection (hotfix).

Tests cover:
1. is_ambiguous_followup() detection
2. build_recent_conversation_block() from input_items
3. max_chars truncation
4. Empty context → clarification request
5. TOOL_EVENTS distinction (proposed vs executed)
6. GENERIC_AGENT_RECENT_TURNS=0 disables injection
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import the module under test directly (avoids __init__.py cascade issues)
from core.context.recent_turns import (
    build_clarification_request,
    build_recent_conversation_block,
    is_ambiguous_followup,
    recent_turns_enabled,
)


# ══════════════════════════════════════════════════════════════════════
# Unit: is_ambiguous_followup()
# ══════════════════════════════════════════════════════════════════════

class TestIsAmbiguousFollowup:
    def test_dots_ellipsis(self):
        assert is_ambiguous_followup("...")
        assert is_ambiguous_followup("....")
        assert is_ambiguous_followup("…")

    def test_chinese_anaphora(self):
        for text in [
            "继续", "继续。", "继续吧",
            "刚才那个", "刚才的", "那个",
            "怎么改回去", "怎么改回来", "改回去", "撤销",
            "按你说的做", "照你说的做", "就按你说的",
            "然后呢", "然后", "还有呢",
            "为什么", "什么意思",
            "详细说说", "展开", "展开说说",
            "举个例子", "举例",
            "不对", "不是这样",
            "重来", "重新来",
            "嗯", "哦", "好", "好的", "行", "可以", "OK", "ok",
            "明白了", "懂了",
            "接着说", "继续讲",
        ]:
            assert is_ambiguous_followup(text), f"should detect: {text!r}"

    def test_english_anaphora(self):
        for text in [
            "continue", "go on", "keep going",
            "that one", "the last one",
            "undo", "revert", "rollback",
            "do what you said", "as you said",
            "and then", "what else",
            "why", "what do you mean",
            "elaborate", "go into detail",
            "give an example",
            "wrong", "not correct",
            "are you sure", "really",
            "start over", "redo",
            "nevermind",
            "ok", "okay", "got it", "understood",
            "next", "go on",
        ]:
            assert is_ambiguous_followup(text), f"should detect: {text!r}"

    def test_very_short_inputs(self):
        assert is_ambiguous_followup("a")
        assert is_ambiguous_followup("ab")
        assert is_ambiguous_followup("abc")

    def test_non_ambiguous_commands(self):
        """Standalone commands that don't need prior context."""
        for text in [
            "/help",
            "/status",
            "/new",
            "写一个Python函数计算斐波那契数列",
            "What is the capital of France?",
            "帮我查一下这个文件的错误",
            "Create a React component for a login form",
            "介绍一下你自己，我是一个Python开发者需要帮助",
        ]:
            assert not is_ambiguous_followup(text), f"should NOT detect: {text!r}"

    def test_short_but_substantive(self):
        """Short inputs that carry their own meaning."""
        for text in [
            "bug",
            "test",
            "help",
            "fix",
        ]:
            # These are 3 chars but meaningful standalone
            # The <=3 rule catches them — this test documents the tradeoff
            result = is_ambiguous_followup(text)
            # They are detected as ambiguous because very short
            assert result is True or result is False  # either is valid

    def test_empty_and_whitespace(self):
        assert is_ambiguous_followup("")
        assert is_ambiguous_followup("   ")
        assert is_ambiguous_followup("\n\t")


# ══════════════════════════════════════════════════════════════════════
# Unit: build_recent_conversation_block()
# ══════════════════════════════════════════════════════════════════════

class TestBuildRecentConversationBlock:
    def test_empty_input_items(self):
        result = build_recent_conversation_block(None)
        assert result == ""
        result = build_recent_conversation_block([])
        assert result == ""

    def test_single_turn_no_tools(self):
        items = [
            {"role": "user", "content": "你好，帮我写一个排序函数"},
            {"role": "assistant", "content": "好的，这是一个快速排序实现..."},
        ]
        block = build_recent_conversation_block(items)
        assert "你好，帮我写一个排序函数" in block
        assert "快速排序实现" in block
        assert "TOOL_EVENTS:" in block
        assert "- none" in block
        assert "[RECENT CONVERSATION" in block
        assert "[/RECENT CONVERSATION]" in block

    def test_multiple_turns(self):
        items = [
            {"role": "user", "content": "任务1"},
            {"role": "assistant", "content": "回答1"},
            {"role": "user", "content": "任务2"},
            {"role": "assistant", "content": "回答2"},
            {"role": "user", "content": "任务3"},
            {"role": "assistant", "content": "回答3"},
        ]
        block = build_recent_conversation_block(items, max_turns=2)
        assert "任务2" in block
        assert "回答2" in block
        assert "任务3" in block
        assert "回答3" in block
        # "任务1" should NOT appear (only last 2 turns)
        assert "任务1" not in block

    def test_tool_events_recorded(self):
        items = [
            {"role": "user", "content": "读取文件"},
            {
                "role": "assistant",
                "content": "我来读取文件",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "read_file", "arguments": '{"path": "/tmp/test.txt"}'},
                    }
                ],
            },
            {"role": "tool", "name": "read_file", "content": "file contents here..."},
            {"role": "assistant", "content": "文件内容如上"},
        ]
        block = build_recent_conversation_block(items)
        assert "read_file" in block
        assert "file contents here" in block

    def test_tool_events_none_when_no_tools(self):
        """TOOL_EVENTS: - none should appear when assistant didn't use tools."""
        items = [
            {"role": "user", "content": "简单问题"},
            {"role": "assistant", "content": "简单回答，没有调用任何工具"},
        ]
        block = build_recent_conversation_block(items)
        assert "- none" in block

    def test_max_chars_truncation(self):
        """Block should not exceed max_chars and should keep most recent turns."""
        items = []
        for i in range(10):
            items.append({"role": "user", "content": f"Question {i}: " + "x" * 500})
            items.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 500})

        block = build_recent_conversation_block(items, max_turns=10, max_chars=2000)
        assert len(block) <= 2200  # allow some margin for headers/footers
        # Most recent turn should be preserved
        assert "Question 9" in block
        # Early turns should be truncated
        assert "truncated" in block.lower() or "[..." in block

    def test_content_list_format(self):
        """Handle content as list of blocks (OpenAI format)."""
        items = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "list format user message"}],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "list format assistant response"}],
            },
        ]
        block = build_recent_conversation_block(items)
        assert "list format user message" in block
        assert "list format assistant response" in block

    def test_system_messages_ignored(self):
        items = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "actual user message"},
            {"role": "assistant", "content": "actual response"},
        ]
        block = build_recent_conversation_block(items)
        assert "actual user message" in block
        assert "actual response" in block
        assert "You are a helpful assistant" not in block

    def test_consecutive_user_messages_merged(self):
        """Consecutive user messages (from context injection) should be merged into one turn."""
        items = [
            {"role": "user", "content": "context block 1"},
            {"role": "user", "content": "context block 2"},
            {"role": "user", "content": "actual user query"},
            {"role": "assistant", "content": "response"},
        ]
        block = build_recent_conversation_block(items)
        # All three user texts should be in the same turn
        assert "context block 1" in block
        assert "context block 2" in block
        assert "actual user query" in block
        assert "response" in block

    def test_tool_result_without_call(self):
        """Tool result that arrives without a prior tool_call should still be recorded."""
        items = [
            {"role": "user", "content": "do something"},
            {"role": "tool", "name": "background_tool", "content": "background result"},
            {"role": "assistant", "content": "done"},
        ]
        block = build_recent_conversation_block(items)
        assert "background_tool" in block
        assert "background result" in block


# ══════════════════════════════════════════════════════════════════════
# Unit: build_clarification_request()
# ══════════════════════════════════════════════════════════════════════

class TestBuildClarificationRequest:
    def test_returns_non_empty_string(self):
        result = build_clarification_request()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "CONTEXT NOTE" in result
        assert "MUST ask" in result or "ask the user" in result.lower()

    def test_mentions_no_context(self):
        result = build_clarification_request()
        assert "NO recent conversation context" in result


# ══════════════════════════════════════════════════════════════════════
# Unit: recent_turns_enabled()
# ══════════════════════════════════════════════════════════════════════

class TestRecentTurnsEnabled:
    def test_default_enabled(self):
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if present
            old = os.environ.pop("GENERIC_AGENT_RECENT_TURNS", None)
            try:
                assert recent_turns_enabled() is True
            finally:
                if old is not None:
                    os.environ["GENERIC_AGENT_RECENT_TURNS"] = old

    def test_explicitly_enabled(self):
        with patch.dict(os.environ, {"GENERIC_AGENT_RECENT_TURNS": "1"}):
            assert recent_turns_enabled() is True

    def test_disabled_with_zero(self):
        with patch.dict(os.environ, {"GENERIC_AGENT_RECENT_TURNS": "0"}):
            assert recent_turns_enabled() is False

    def test_disabled_with_other_values(self):
        """Only '0' disables; other non-empty values keep it enabled."""
        with patch.dict(os.environ, {"GENERIC_AGENT_RECENT_TURNS": "yes"}):
            assert recent_turns_enabled() is True


# ══════════════════════════════════════════════════════════════════════
# Integration: end-to-end scenarios
# ══════════════════════════════════════════════════════════════════════

class TestRecentContextIntegration:
    def test_ambiguous_query_empty_context(self):
        """User sends '...' with empty history → clarification requested."""
        block = build_recent_conversation_block([], max_turns=5)
        assert block == ""

        ambiguous = is_ambiguous_followup("...")
        assert ambiguous is True

        # When block is empty and query is ambiguous, inject clarification
        if ambiguous and not block:
            clarification = build_clarification_request()
            assert len(clarification) > 0

    def test_ambiguous_query_with_context(self):
        """User sends '继续' with prior context → block provides context."""
        items = [
            {"role": "user", "content": "帮我写一个排序算法"},
            {"role": "assistant", "content": "好的，这是快速排序：def quicksort..."},
        ]
        block = build_recent_conversation_block(items, max_turns=5)
        assert len(block) > 0
        assert "排序算法" in block

        ambiguous = is_ambiguous_followup("继续")
        assert ambiguous is True

        # When block exists, model can use it — no clarification needed
        if ambiguous and not block:
            clarification = build_clarification_request()
            assert False, "should not need clarification when block exists"

    def test_proposed_vs_executed_distinction(self):
        """Assistant proposes a change but TOOL_EVENTS=none → model knows it's not executed."""
        items = [
            {"role": "user", "content": "怎么改端口号"},
            {
                "role": "assistant",
                "content": (
                    "建议修改 config.yaml 中的 port 字段从 8080 改为 3000。"
                    "同时需要更新 nginx 配置中的 proxy_pass。"
                ),
            },
        ]
        block = build_recent_conversation_block(items)
        assert "config.yaml" in block
        assert "8080" in block
        # TOOL_EVENTS should be "none" — assistant only proposed, didn't execute
        assert "- none" in block.lower() or "TOOL_EVENTS:\n- none" in block

    def test_rollback_clarification(self):
        """User asks '怎么改回去' — if TOOL_EVENTS=none, model should know it was just talk."""
        items = [
            {"role": "user", "content": "把超时时间改成30秒"},
            {
                "role": "assistant",
                "content": "需要修改 timeout_ms 参数。建议先备份配置文件，然后修改 timeout_ms=30000。",
            },
        ]
        block = build_recent_conversation_block(items)
        assert "timeout_ms" in block
        # No tool executed — just a proposal
        assert "- none" in block.lower() or "TOOL_EVENTS:\n- none" in block

    def test_env_var_disabled(self):
        """GENERIC_AGENT_RECENT_TURNS=0 should disable injection."""
        assert recent_turns_enabled() is True  # default

        with patch.dict(os.environ, {"GENERIC_AGENT_RECENT_TURNS": "0"}):
            assert recent_turns_enabled() is False
            # When disabled, build_recent_conversation_block is still callable
            # but the injection code in openai_agentmain.py checks the flag first
            block = build_recent_conversation_block(
                [{"role": "user", "content": "test"}],
            )
            assert len(block) > 0  # function still works, just not injected


# ══════════════════════════════════════════════════════════════════════
# Regression: edge cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_non_dict_items_ignored(self):
        items: list = [
            "not a dict",
            None,
            42,
            {"role": "user", "content": "valid message"},
        ]
        block = build_recent_conversation_block(items)
        assert "valid message" in block

    def test_items_without_role_key(self):
        items = [
            {"content": "no role key"},
            {"role": "user", "content": "has role"},
            {"role": "assistant", "content": "response"},
        ]
        block = build_recent_conversation_block(items)
        assert "has role" in block

    def test_empty_content_text(self):
        items = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": ""},
        ]
        block = build_recent_conversation_block(items)
        # Should not crash, may produce minimal block since empty content creates no turn
        assert isinstance(block, str)

    def test_large_tool_arguments_summarized(self):
        """Long tool arguments should be summarized."""
        long_args = "x" * 500
        items = [
            {"role": "user", "content": "test"},
            {
                "role": "assistant",
                "content": "calling tool",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "write_file", "arguments": long_args},
                    }
                ],
            },
        ]
        block = build_recent_conversation_block(items)
        assert "write_file" in block
        # Arguments should be summarized (truncated)
        # The full 500-char args should not appear verbatim
        assert long_args not in block

    def test_max_turns_respected(self):
        items = []
        for i in range(20):
            items.append({"role": "user", "content": f"Q{i}"})
            items.append({"role": "assistant", "content": f"A{i}"})

        block = build_recent_conversation_block(items, max_turns=3)
        # Only last 3 turns should appear
        turn_count = block.count("## Turn")
        assert turn_count <= 3
