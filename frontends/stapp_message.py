"""Message rendering utilities extracted from stapp.py.

``render_segments`` is the only function that depends on Streamlit;
the others are pure text-processing helpers.
"""

from __future__ import annotations

import re

import streamlit as st

from frontends.chatapp_common import clean_reply


def message_content_to_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in ("text", "input_text", "output_text"):
                text = block.get("text", "")
                if text:
                    parts.append(str(text))
            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, str) and tool_content:
                    parts.append(tool_content)
        return "\n".join(parts)
    if isinstance(content, dict):
        return str(content.get("text", "") or content.get("content", "") or "")
    return str(content or "")


def sanitize_streaming_tail(text):
    """Strip incomplete markdown from the trailing end of streaming text."""
    if not text:
        return text

    # ── Unclosed fenced code blocks (```) ──
    lines = text.split("\n")
    fence_lines = [i for i, l in enumerate(lines) if l.startswith("```")]
    if len(fence_lines) % 2 != 0:
        text = "\n".join(lines[: fence_lines[-1]])

    # ── Unclosed bold markers ──
    if text.count("**") % 2 != 0:
        last_double = text.rfind("**")
        text = text[:last_double]

    # ── Unclosed inline code ──
    non_fence = text
    while "```" in non_fence:
        non_fence = non_fence.replace("```", "", 1)
    if non_fence.count("`") % 2 != 0:
        last_tick = text.rfind("`")
        if not text[last_tick : last_tick + 3].startswith("```"):
            text = text[:last_tick]

    return text


def fold_turns(text):
    """Split multi-turn response into segments: text / fold."""
    text = message_content_to_text(text)
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
            stripped = re.sub(
                r"```.*?```|<thinking>.*?</thinking>", "", content, flags=re.DOTALL
            )
            matches = re.findall(
                r"<summary>\s*((?:(?!<summary>).)*?)\s*</summary>", stripped, re.DOTALL
            )
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


def render_segments(segments, suffix="", fold_expanded=False):
    for seg in segments:
        if seg["type"] == "fold":
            with st.expander(seg["title"], expanded=fold_expanded):
                st.markdown(clean_reply(seg["content"]))
        else:
            st.markdown(clean_reply(seg["content"]) + suffix)


def should_show_live_turn(text, turn):
    if not turn:
        return False
    text = message_content_to_text(text)
    return f"Turn {turn}" not in text
