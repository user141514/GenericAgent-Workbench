"""Tests for core.openai_runtime.message_conversion -- pure message transform functions."""
from __future__ import annotations

import pytest
from core.openai_runtime.message_conversion import (
    _chat_messages_to_claude_messages,
    _extract_classic_executor_report,
    _inject_turn_markers,
    _input_items_to_history_lines,
    _latest_turn_marker,
    _message_content_to_claude_blocks,
    _restored_lines_to_inputs,
    _tool_message_content_to_text,
)


# -- _restored_lines_to_inputs --

def test_restored_lines_to_inputs_basic():
    restored = ["[USER]: hello", "[Agent] hi there", "[USER]: thanks"]
    result = _restored_lines_to_inputs(restored)
    assert result == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "thanks"},
    ]


def test_restored_lines_to_inputs_empty():
    assert _restored_lines_to_inputs([]) == []


def test_restored_lines_to_inputs_skips_unknown_prefix():
    restored = ["[SYSTEM]: beep", "[USER]: hello"]
    result = _restored_lines_to_inputs(restored)
    assert result == [{"role": "user", "content": "hello"}]


# -- _input_items_to_history_lines --

def test_input_items_to_history_lines_basic():
    items = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    result = _input_items_to_history_lines(items)
    assert result == ["[USER]: hello", "[Agent] world"]


def test_input_items_to_history_lines_merges_same_role():
    items = [
        {"role": "user", "content": "msg1"},
        {"role": "user", "content": "msg2"},
    ]
    result = _input_items_to_history_lines(items)
    assert result == ["[USER]: msg1\n\nmsg2"]


def test_input_items_to_history_lines_skips_empty():
    items = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "  "},
    ]
    assert _input_items_to_history_lines(items) == []


def test_input_items_to_history_lines_skips_non_dict():
    items = ["a", None, {"role": "user", "content": "ok"}]
    result = _input_items_to_history_lines(items)
    assert result == ["[USER]: ok"]


# -- _message_content_to_claude_blocks --

def test_message_content_to_claude_blocks_string():
    assert _message_content_to_claude_blocks("hello") == [{"type": "text", "text": "hello"}]


def test_message_content_to_claude_blocks_none():
    assert _message_content_to_claude_blocks(None) == []


def test_message_content_to_claude_blocks_mixed_list():
    content = [
        "text part",
        {"type": "text", "text": "block text"},
        {"type": "image_url", "image_url": {"url": "http://img"}},
        {"type": "refusal", "refusal": "no"},
    ]
    result = _message_content_to_claude_blocks(content)
    assert len(result) == 4
    assert result[0] == {"type": "text", "text": "text part"}
    assert result[2] == {"type": "text", "text": "[image] http://img"}
    assert result[3] == {"type": "text", "text": "no"}


# -- _tool_message_content_to_text --

def test_tool_message_content_to_text_string():
    assert _tool_message_content_to_text("plain") == "plain"


def test_tool_message_content_to_text_content_list():
    content = [
        {"type": "text", "text": "hello"},
        {"type": "input_text", "text": "world"},
    ]
    assert _tool_message_content_to_text(content) == "hello\nworld"


# -- _chat_messages_to_claude_messages --

def test_chat_to_claude_simple():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    result = _chat_messages_to_claude_messages(messages)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == [{"type": "text", "text": "hello"}]


def test_chat_to_claude_with_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "search", "arguments": '{"q":"test"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result text"},
    ]
    result = _chat_messages_to_claude_messages(messages)
    # assistant with tool_use block
    assert result[0]["role"] == "assistant"
    assert result[0]["content"][0]["type"] == "tool_use"
    assert result[0]["content"][0]["name"] == "search"
    # tool result as user message
    assert result[1]["role"] == "user"
    assert result[1]["content"][0]["type"] == "tool_result"
    assert result[1]["content"][0]["content"] == "result text"


def test_chat_to_claude_skips_system():
    messages = [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "hi"},
    ]
    result = _chat_messages_to_claude_messages(messages)
    assert len(result) == 1
    assert result[0]["role"] == "user"


# -- _inject_turn_markers --

def test_inject_turn_markers_plain():
    result = _inject_turn_markers("hello world")
    assert "LLM Running (Turn 1)" in result
    assert "hello world" in result


def test_inject_turn_markers_skips_if_present():
    text = "LLM Running (Turn 5) ... already present"
    assert _inject_turn_markers(text) == text


def test_inject_turn_markers_with_sections():
    text = "Plan:\ndo stuff\nExecution:\nrun it"
    result = _inject_turn_markers(text)
    assert "Turn 1" in result
    assert "Turn 2" in result


# -- _latest_turn_marker --

def test_latest_turn_marker():
    text = "LLM Running (Turn 1)...text...LLM Running (Turn 3)...more"
    assert _latest_turn_marker(text) == 3


def test_latest_turn_marker_none():
    assert _latest_turn_marker("") == 0
    assert _latest_turn_marker("no markers") == 0


# -- _extract_classic_executor_report --

def test_extract_classic_executor_report_summary_tail():
    """Returns text after the last </summary> tag."""
    text = "<thinking>...</thinking>\n<summary>blah</summary>\nmore text"
    result = _extract_classic_executor_report(text)
    assert result == "more text"


def test_extract_classic_executor_report_turn_sections():
    """Returns last section after splitting by LLM Running markers."""
    text = "**LLM Running (Turn 1) ...**\n\nfirst section\n\n**LLM Running (Turn 2) ...**\n\nsecond section"
    result = _extract_classic_executor_report(text)
    assert result == "second section"


def test_extract_classic_executor_report_no_markers():
    text = "just plain text"
    assert _extract_classic_executor_report(text) == "just plain text"