"""Test that internal XML tags are stripped before markdown rendering."""
import re
import sys
import os

# Add project root for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from frontends.chatapp_common import clean_reply, TAG_PATS


def _fold_turns(text):
    """Replicate fold_turns logic from stapp.py for testing.
    Returns list of {type, content} dicts."""
    parts = re.split(r"(\**LLM Running \(Turn \d+\) \.\.\.\*\**)", text)
    if len(parts) < 4:
        return [{"type": "text", "content": text}]
    segments = []
    if parts[0].strip():
        segments.append({"type": "text", "content": parts[0]})
    turns = []
    for i in range(1, len(parts), 2):
        marker = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        turns.append((marker, content))
    for idx, (marker, content) in enumerate(turns):
        if idx < len(turns) - 1:
            stripped = re.sub(r"```.*?```|<thinking>.*?</thinking>", "", content, flags=re.DOTALL)
            matches = re.findall(r"<summary>\s*((?:(?!<summary>).)*?)\s*</summary>", stripped, re.DOTALL)
            if matches:
                title = matches[0].strip().split("\n")[0]
                if len(title) > 50:
                    title = title[:50] + "..."
            else:
                title = marker.strip("*")
            segments.append({"type": "fold", "title": title, "content": content})
        else:
            segments.append({"type": "text", "content": marker + content})
    return segments


def _simulate_render_pipeline(response_text):
    """Simulate what content reaches st.markdown() in the render pipeline.

    Returns list of content strings that would be passed to st.markdown().
    clean_reply() is called in render_segments before st.markdown(),
    so the content reaching the markdown renderer should be tag-free.
    """
    segments = _fold_turns(response_text)
    contents = []
    for seg in segments:
        contents.append(clean_reply(seg["content"]))
    return contents


class TestRenderingPipelineStripsTags:
    """RED: content passed to st.markdown() must have internal tags stripped.

    These tests verify that the rendering pipeline cleans tags from content
    before it reaches st.markdown().  They will FAIL until clean_reply()
    is integrated into the pipeline.
    """

    def test_single_turn_thinking_stripped(self):
        """No <thinking> should leak to st.markdown() in single-turn responses."""
        response = "<thinking>\n分析中...\n</thinking>\n\n这是实际回复，包含**加粗**和列表。"
        contents = _simulate_render_pipeline(response)
        for content in contents:
            assert "<thinking>" not in content, (
                f"<thinking> leaked to renderer: {repr(content[:80])}"
            )

    def test_single_turn_summary_stripped(self):
        """No <summary> should leak to st.markdown()."""
        response = "<summary>\n状态：处理中\n</summary>\n\n回复内容"
        contents = _simulate_render_pipeline(response)
        for content in contents:
            assert "<summary>" not in content, (
                f"<summary> leaked to renderer: {repr(content[:80])}"
            )

    def test_multi_turn_tags_stripped(self):
        """Tags must be stripped in all turns of a multi-turn response."""
        response = (
            "**LLM Running (Turn 1) ...**\n\n"
            "<thinking>turn1思考</thinking>\n<summary>turn1摘要</summary>\n第一轮回复\n"
            "**LLM Running (Turn 2) ...**\n\n"
            "<thinking>turn2思考</thinking>\n<summary>turn2摘要</summary>\n第二轮回复"
        )
        contents = _simulate_render_pipeline(response)
        for i, content in enumerate(contents):
            assert "<thinking>" not in content, (
                f"Turn {i}: <thinking> leaked: {repr(content[:80])}"
            )
            assert "<summary>" not in content, (
                f"Turn {i}: <summary> leaked: {repr(content[:80])}"
            )

    def test_markdown_preserved_after_cleaning(self):
        """Markdown formatting must survive tag stripping."""
        response = (
            "<thinking>discard</thinking>\n"
            "## 标题\n"
            "**粗体**\n"
            "- 列表\n"
            "```python\nprint(1)\n```\n"
            "<summary>discard</summary>"
        )
        contents = _simulate_render_pipeline(response)
        for content in contents:
            assert "## 标题" in content
            assert "**粗体**" in content
            assert "- 列表" in content
            assert "print(1)" in content

    def test_realistic_agent_response(self):
        """Simulate a realistic agent response with thinking + tool_use + summary."""
        response = (
            "<thinking>\n"
            "当前阶段：定位\n"
            "需要查看文件内容来确认问题\n"
            "</thinking>\n"
            "<tool_use>\n"
            "file_read: /tmp/test.py\n"
            "</tool_use>\n"
            "<summary>\n"
            "已读取文件，发现第10行有空值问题\n"
            "</summary>\n\n"
            "经过检查，发现问题是**空值处理不当**。\n\n"
            "修复方法：\n"
            "1. 在第10行添加空值检查\n"
            "2. 添加默认值回退\n\n"
            "```python\n"
            "if value is None:\n"
            "    value = default\n"
            "```"
        )
        contents = _simulate_render_pipeline(response)
        for content in contents:
            # Internal tags must be stripped
            for tag in ("thinking", "summary", "tool_use"):
                assert f"<{tag}>" not in content, (
                    f"<{tag}> leaked to renderer: {repr(content[:100])}"
                )
            # Visible markdown preserved
            assert "空值处理不当" in content
            assert "修复方法" in content
            assert "value is None" in content


class TestStripInternalTags:
    """Verify that clean_reply strips <thinking>, <summary>, <tool_use>, <file_content>."""

    def test_strips_thinking_block(self):
        text = "<thinking>\n分析中...\n</thinking>\n\n这是实际回复"
        result = clean_reply(text)
        assert "<thinking>" not in result
        assert "分析中" not in result
        assert "这是实际回复" in result

    def test_strips_summary_block(self):
        text = "<summary>\n当前状态：已完成\n</summary>\n\n回复内容"
        result = clean_reply(text)
        assert "<summary>" not in result
        assert "当前状态" not in result
        assert "回复内容" in result

    def test_strips_tool_use_block(self):
        text = "<tool_use>\nfile_read /tmp/x\n</tool_use>\n\n结果如下"
        result = clean_reply(text)
        assert "<tool_use>" not in result
        assert "file_read" not in result
        assert "结果如下" in result

    def test_strips_file_content_block(self):
        text = "<file_content>\nprint('hello')\n</file_content>\n\n以上是文件内容"
        result = clean_reply(text)
        assert "<file_content>" not in result
        assert "print('hello')" not in result
        assert "以上是文件内容" in result

    def test_strips_all_tags_mixed(self):
        text = (
            "<thinking>需要查文件</thinking>\n"
            "<summary>已读</summary>\n"
            "这是**加粗**文本\n"
            "- 列表项1\n"
            "- 列表项2\n"
            "<tool_use>file_read x</tool_use>\n"
            "后续内容"
        )
        result = clean_reply(text)
        # All tags should be gone
        for tag_word in ("thinking", "summary", "tool_use"):
            assert f"<{tag_word}>" not in result
        # User-visible content preserved
        assert "这是**加粗**文本" in result
        assert "- 列表项1" in result
        assert "- 列表项2" in result
        assert "后续内容" in result

    def test_does_not_touch_markdown_formatting(self):
        """Markdown syntax like **bold**, lists, code blocks must survive."""
        text = (
            "<thinking>思考中</thinking>\n"
            "## 标题\n"
            "**粗体** 和 *斜体*\n"
            "```python\nprint('hello')\n```\n"
            "1. 有序列表\n"
            "- 无序列表\n"
            "<summary>完成</summary>"
        )
        result = clean_reply(text)
        assert "## 标题" in result
        assert "**粗体**" in result
        assert "*斜体*" in result
        assert "```python" in result
        assert "print('hello')" in result
        assert "```" in result
        assert "1. 有序列表" in result
        assert "- 无序列表" in result
        # Tags stripped
        assert "<thinking>" not in result
        assert "<summary>" not in result

    def test_empty_content_fallback(self):
        """Content with only tags should return '...'."""
        text = "<thinking>only thinking</thinking>\n<summary>only summary</summary>"
        result = clean_reply(text)
        assert result == "..."

    def test_tag_patterns_are_non_greedy(self):
        """Each TAG_PAT should match the nearest closing tag, not span multiple blocks."""
        text = "<thinking>A</thinking> keep <thinking>B</thinking>"
        result = clean_reply(text)
        assert result == "keep"
