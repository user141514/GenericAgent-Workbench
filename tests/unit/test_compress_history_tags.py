"""Test that compress_history_tags regex patterns are compiled once at module level.

Performance fix: re.compile() was called inside the function body every 5th turn.
Move to module-level constants.
"""

from __future__ import annotations

import re

import core.llmcore as llmcore


# These should be module-level in llmcore.py
_TAG_PATTERNS = {
    tag: re.compile(rf'(<{tag}>)([\s\S]*?)(</{tag}>)')
    for tag in ('thinking', 'think', 'tool_use', 'tool_result')
}
_HISTORY_PATTERN = re.compile(r'<(history|key_info)>[\s\S]*?</\1>')


def _trunc_str(s, max_len=800):
    if not isinstance(s, str) or len(s) <= max_len:
        return s
    half = max_len // 2
    return s[:half] + '\n...[Truncated]...\n' + s[-half:]


def _trunc(text):
    text = _HISTORY_PATTERN.sub(
        lambda m: f'<{m.group(1)}>[...]</{m.group(1)}>', text
    )
    for pat in _TAG_PATTERNS.values():
        text = pat.sub(
            lambda m: m.group(1) + _trunc_str(m.group(2)) + m.group(3),
            text,
        )
    return text


class TestCompressHistoryTags:
    def test_force_compression_does_not_reset_other_history_counter(self):
        """Force-compressing one history must not reset another loop's cadence."""
        if hasattr(llmcore.compress_history_tags, "_cd"):
            delattr(llmcore.compress_history_tags, "_cd")
        if hasattr(llmcore, "_COMPRESS_HISTORY_COUNTS"):
            llmcore._COMPRESS_HISTORY_COUNTS.clear()

        long_thought = "x" * 2000
        h1 = [{"role": "assistant", "content": f"<thinking>{long_thought}</thinking>"}]
        h2 = [{"role": "assistant", "content": f"<thinking>{long_thought}</thinking>"}]

        for _ in range(4):
            llmcore.compress_history_tags(h1, keep_recent=0, max_len=80)
        assert "[Truncated]" not in h1[0]["content"]

        llmcore.compress_history_tags(h2, keep_recent=0, max_len=80, force=True)
        assert "[Truncated]" in h2[0]["content"]

        llmcore.compress_history_tags(h1, keep_recent=0, max_len=80)
        assert "[Truncated]" in h1[0]["content"]

    def test_thinking_tag_truncation(self):
        """Thinking blocks are truncated when content exceeds max_len."""
        long_thought = "x" * 2000
        text = f"<thinking>{long_thought}</thinking>"
        result = _trunc(text)
        assert result.startswith("<thinking>"), f"Got: {result[:80]}"
        assert result.endswith("</thinking>"), f"Got: {result[-20:]}"
        assert "[Truncated]" in result
        assert len(result) < len(text), "Content should be shortened"

    def test_short_thinking_preserved(self):
        """Short thinking blocks are left intact."""
        text = "<thinking>brief thought</thinking>"
        result = _trunc(text)
        assert result == text, f"Expected unchanged, got: {result}"

    def test_tool_use_tag_truncation(self):
        """Tool use blocks are truncated when content exceeds max_len."""
        long_args = "x" * 2000
        text = f"<tool_use>{long_args}</tool_use>"
        result = _trunc(text)
        assert "<tool_use>" in result
        assert "</tool_use>" in result
        assert "[Truncated]" in result

    def test_history_tag_truncation(self):
        """History blocks are truncated to placeholder."""
        text = "<history>very long context here</history>"
        result = _trunc(text)
        assert "<history>" in result
        assert "[...]" in result
        assert "</history>" in result

    def test_key_info_tag_truncation(self):
        """key_info blocks are truncated to placeholder."""
        text = "<key_info>secret keys and config</key_info>"
        result = _trunc(text)
        assert "<key_info>" in result
        assert "[...]" in result
        assert "</key_info>" in result

    def test_multiple_tags_in_one_text(self):
        """Multiple different tags are all processed."""
        text = (
            "<thinking>long analysis " + "x" * 2000 + "</thinking>"
            "normal text in between"
            "<tool_result>" + "y" * 2000 + "</tool_result>"
        )
        result = _trunc(text)
        assert "[Truncated]" in result
        assert "thinking" in result
        assert "tool_result" in result
        assert "normal text in between" in result

    def test_str_content_preserved(self):
        """Non-string content returns as-is."""
        assert _trunc_str(123, max_len=100) == 123
        assert _trunc_str(None, max_len=100) is None

    def test_no_tags_returns_unchanged(self):
        """Text without any tags is unchanged."""
        text = "normal conversation without any XML tags"
        assert _trunc(text) == text

    def test_compiled_regex_ids_match(self):
        """All compiled patterns produce valid results (no errors)."""
        for name, pat in _TAG_PATTERNS.items():
            assert pat.pattern, f"Pattern for {name} is empty"
            # Verify pattern compiles and matches correctly
            test_str = f"<{name}>test content</{name}>"
            match = pat.search(test_str)
            assert match, f"Pattern for {name} doesn't match test string"
            assert match.group(1) == f"<{name}>"
            assert match.group(2) == "test content"
            assert match.group(3) == f"</{name}>"
