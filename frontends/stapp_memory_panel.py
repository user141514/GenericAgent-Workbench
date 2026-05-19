"""Memory panel — extracted from stapp.py render_sidebar().

Displays L1 memory index, L2 global memory, and the candidate inbox.
Pure UI + file reading.  No ``st.session_state`` writes, no agent calls.
"""

from __future__ import annotations

import os

import streamlit as st


def get_memory_content(project_root: str) -> dict[str, str]:
    """Read the three memory files from ``memory/``.

    Args:
        project_root: The project root directory (e.g. ``script_dir/..``).
    """
    mem_dir = os.path.join(project_root, "memory")
    result: dict[str, str] = {}
    for name in (
        "global_mem_insight.txt",
        "global_mem.txt",
        "history_memory_inbox.md",
    ):
        path = os.path.join(mem_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                result[name] = f.read()
    return result


def render_memory_panel(project_root: str) -> None:
    """Render the memory system panel in the Streamlit sidebar.

    Args:
        project_root: The project root directory for ``get_memory_content()``.
    """
    st.subheader("🧠 记忆系统")
    mem_content = get_memory_content(project_root)

    if not mem_content:
        st.info("暂无记忆内容")
        return

    if "global_mem_insight.txt" in mem_content:
        with st.expander("📋 L1: 记忆索引", expanded=True):
            st.markdown(mem_content["global_mem_insight.txt"])

    if "global_mem.txt" in mem_content:
        with st.expander("📖 L2: 全局记忆", expanded=False):
            content = mem_content["global_mem.txt"]
            if content.strip():
                st.markdown(content)
            else:
                st.info("(空)")

    if "history_memory_inbox.md" in mem_content:
        with st.expander("🗂️ 记忆候选池", expanded=False):
            st.caption(
                "这里存放从历史对话中人工确认后提炼出的候选记忆，"
                "还没有自动并入 L1/L2/L3。"
            )
            st.markdown(mem_content["history_memory_inbox.md"])
