"""Message rendering utilities extracted from stapp.py.

``render_segments`` is the only function that depends on Streamlit;
the others are pure text-processing helpers.
"""

from __future__ import annotations

import json
import re

import streamlit as st

from frontends.chatapp_common import clean_reply

TURN_MARKER_RE = re.compile(r"(\**LLM Running \(Turn (\d+)\) \.\.\.\*\**)")


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


def latest_turn_from_text(text) -> int:
    text = message_content_to_text(text)
    matches = TURN_MARKER_RE.findall(text)
    if not matches:
        return 0
    try:
        return int(matches[-1][1])
    except (TypeError, ValueError):
        return 0


def fold_turns(text):
    """Split multi-turn response into segments: text / fold."""
    text = message_content_to_text(text)
    parts = TURN_MARKER_RE.split(text)
    if len(parts) < 4:
        return [{"type": "text", "content": text}]
    segments = []
    if parts[0].strip():
        segments.append({"type": "text", "content": parts[0]})
    turns = []
    for i in range(1, len(parts), 3):
        marker = parts[i]
        content = parts[i + 2] if i + 2 < len(parts) else ""
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
            segments.append({"type": "text", "content": content})
    return segments


def render_segments(segments, suffix="", fold_expanded=False):
    for seg in segments:
        if seg["type"] == "fold":
            with st.expander(seg["title"], expanded=fold_expanded):
                st.markdown(clean_reply(seg["content"]))
        else:
            st.markdown(clean_reply(seg["content"]) + suffix)


def copyable_reply_text(content) -> str:
    """Return the user-visible assistant text used by the copy button."""
    text = message_content_to_text(content)
    segments = fold_turns(text)
    if len(segments) > 1:
        for seg in reversed(segments):
            if seg.get("type") == "text" and seg.get("content", "").strip():
                text = seg["content"]
                break
    return clean_reply(text).strip()


def _copy_button_id(key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(key or "reply"))
    return f"copy_reply_{safe[:80]}"


def build_copy_reply_button_html(content, key: str) -> str:
    text = copyable_reply_text(content)
    payload = json.dumps(text, ensure_ascii=False).replace("</", "<\\/")
    button_id = _copy_button_id(key)
    return f"""
<style>
body {{ margin: 0; background: transparent; }}
.copy-reply-btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 9px;
  border: 1px solid rgba(60, 54, 45, 0.18);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.72);
  color: #6f665a;
  font: 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  cursor: pointer;
}}
.copy-reply-btn:hover {{ background: #fff; color: #4d453b; }}
.copy-reply-btn.copied {{ border-color: rgba(74, 120, 82, 0.38); color: #4a7852; }}
.copy-reply-btn svg {{ width: 14px; height: 14px; flex: 0 0 auto; }}
</style>
<button id="{button_id}" class="copy-reply-btn" type="button" aria-label="复制回复" title="复制回复">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect>
    <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
  </svg>
  <span>复制</span>
</button>
<script>
(function() {{
  const btn = document.getElementById({json.dumps(button_id)});
  const payload = {payload};
  const label = btn && btn.querySelector("span");
  function mark(text) {{
    if (!label) return;
    label.textContent = text;
    btn.classList.add("copied");
    setTimeout(() => {{
      label.textContent = "复制";
      btn.classList.remove("copied");
    }}, 1200);
  }}
  async function fallbackCopy() {{
    const ta = document.createElement("textarea");
    ta.value = payload;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }}
  if (btn) {{
    btn.addEventListener("click", async () => {{
      try {{
        if (navigator.clipboard && window.isSecureContext) {{
          await navigator.clipboard.writeText(payload);
        }} else {{
          await fallbackCopy();
        }}
        mark("已复制");
      }} catch (err) {{
        try {{
          await fallbackCopy();
          mark("已复制");
        }} catch (_) {{
          mark("复制失败");
        }}
      }}
    }});
  }}
}})();
</script>
"""


def render_copy_reply_button(content, key: str) -> None:
    text = copyable_reply_text(content)
    if not text or text == "...":
        return
    from streamlit.components.v1 import html as _html

    _html(build_copy_reply_button_html(content, key), height=34, scrolling=False)


def should_show_live_turn(text, turn):
    del text
    return bool(turn)
