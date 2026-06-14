"""Test _build_protocol_prompt output correctness.

Performance fix: replace O(n^2) string += concatenation with list+join.
"""

from __future__ import annotations

import json

from core.llmcore import ToolClient


class _DummyBackend:
    name = "dummy"
    model = "dummy"

    def ask(self, *_args, **_kwargs):
        raise AssertionError("test must not call backend")


def _tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


class TestBuildProtocolPrompt:
    def test_basic_output_format(self):
        """Output contains system content, user/assistant markers, and AI prompt."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        prompt = client._build_protocol_prompt(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            _tools(),
        )

        assert "You are helpful." in prompt
        assert "=== USER ===" in prompt
        assert "Hello" in prompt
        assert "=== ASSISTANT ===" in prompt
        assert prompt.count("=== USER ===") == 1

    def test_multi_turn_conversation(self):
        """Multi-turn conversation preserves all messages in order."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        prompt = client._build_protocol_prompt(
            [
                {"role": "system", "content": "System"},
                {"role": "user", "content": "Q1"},
                {"role": "assistant", "content": "A1"},
                {"role": "user", "content": "Q2"},
                {"role": "assistant", "content": "A2"},
                {"role": "user", "content": "Q3"},
            ],
            _tools(),
        )

        # Order preserved
        q1_pos = prompt.index("Q1")
        a1_pos = prompt.index("A1")
        q2_pos = prompt.index("Q2")
        a2_pos = prompt.index("A2")
        q3_pos = prompt.index("Q3")
        assert q1_pos < a1_pos < q2_pos < a2_pos < q3_pos

    def test_tool_results_included(self):
        """Tool results from user messages are rendered as <tool_result>."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        prompt = client._build_protocol_prompt(
            [
                {"role": "system", "content": "S"},
                {
                    "role": "user",
                    "content": "Next",
                    "tool_results": [
                        {"tool_use_id": "t1", "content": "result content here"}
                    ],
                },
            ],
            _tools(),
        )

        assert "<tool_result>" in prompt
        assert "result content here" in prompt

    def test_large_history_no_corruption(self):
        """Large history (50 messages) produces complete output with no truncation."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        messages = [{"role": "system", "content": "S"}]
        for i in range(25):
            messages.append({"role": "user", "content": f"Question number {i}"})
            messages.append({"role": "assistant", "content": f"Answer number {i}"})

        prompt = client._build_protocol_prompt(messages, _tools())

        # All messages present
        for i in range(25):
            assert f"Question number {i}" in prompt, f"Missing question {i}"
            assert f"Answer number {i}" in prompt, f"Missing answer {i}"

        # Correct number of markers
        assert prompt.count("=== USER ===") == 25
        assert prompt.count("=== ASSISTANT ===\n") == 26  # 25 answers + final prompt line

    def test_empty_tools_produces_no_tool_section(self):
        """No tools means no tools JSON in output."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        prompt = client._build_protocol_prompt(
            [
                {"role": "system", "content": "minimal"},
                {"role": "user", "content": "hi"},
            ],
            [],
        )
        assert "file_read" not in prompt

    def test_non_string_content_serialized(self):
        """Non-string content values are str()-converted."""
        client = ToolClient(_DummyBackend(), auto_save_tokens=True)
        prompt = client._build_protocol_prompt(
            [
                {"role": "system", "content": "S"},
                {"role": "user", "content": 12345},
            ],
            _tools(),
        )
        assert "12345" in prompt
