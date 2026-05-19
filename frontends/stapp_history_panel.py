"""Distill preview panel — extracted from stapp.py.

Renders the distillation preview expander with "write to memory" and "close"
buttons.  This is a Streamlit UI module, not a service.
"""

from __future__ import annotations

import streamlit as st


def render_distill_preview(summary, filepath, fname, *, state=None) -> None:
    """Render the distillation preview expander.

    Args:
        summary: dict from ``distill_conversation()``.
        filepath: source history file path.
        fname: base filename for the session_state key.
        state: dict-like (defaults to ``st.session_state``).
               Must support ``state[key] = None`` and ``state.get(key)``.
    """
    if state is None:
        state = st.session_state

    from frontends.chatapp_common import save_distilled_memory

    title = summary.get("title", fname)[:30]
    with st.expander(f"📝 提炼预览: {title}", expanded=True):
        st.markdown(f"**标题:** {summary.get('title', fname)}")
        st.markdown(f"**轮次:** {summary.get('rounds', 0)}")

        if summary.get("questions"):
            st.markdown("**用户问题:**")
            for q in summary["questions"][:5]:
                st.text(f"- {q[:80]}")

        if summary.get("files_touched"):
            st.markdown("**涉及文件:**")
            for p in summary["files_touched"][:10]:
                st.text(f"- {p}")

        if summary.get("key_replies"):
            st.markdown("**关键回复:**")
            for r in summary["key_replies"][:3]:
                st.text(f"- {r[:100]}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("写入记忆", key=f"confirm_{fname}", use_container_width=True):
                result, save_err = save_distilled_memory(summary, filepath)
                if result:
                    st.success(f"已写入: {summary.get('title', fname)[:30]}")
                else:
                    st.error(f"保存失败: {save_err}")
                state[f"distill_result_{fname}"] = None
                st.rerun()
        with col_b:
            if st.button("关闭", key=f"cancel_{fname}", use_container_width=True):
                state[f"distill_result_{fname}"] = None
                st.rerun()
