"""Upload panel — extracted from stapp.py render_sidebar().

Renders the file uploader widget, processes uploads via ``FileUploadService``,
and displays the attachment list.  This is a Streamlit UI panel, not a service.
"""

from __future__ import annotations

import streamlit as st


# ── bridge functions (minimal session_state coupling) ────────────────────

def sync_uploaded_files(
    uploaded_items,
    cache: dict,
    *,
    on_spinner=None,
) -> list[dict]:
    """Process uploaded files, returning a list of result dicts.

    Does NOT write ``st.session_state`` directly.  The caller is responsible
    for storing the returned list (e.g. ``state.uploaded_files = result``).

    Args:
        uploaded_items: list of Streamlit ``UploadedFile`` objects.
        cache: dict used for dedup (e.g. ``st.session_state.processed_upload_cache``).
        on_spinner: optional ``(filename) -> contextmanager`` for progress display.
    """
    from frontends.services.file_upload_service import FileUploadService

    service = FileUploadService(cache=cache)
    items = uploaded_items or []
    if on_spinner and items:
        results = service.process(items, on_progress=on_spinner)
    else:
        results = service.process(items)
    return [r.to_dict() for r in results]


def clear_uploaded_files(state) -> None:
    """Reset upload state on *state* (a dict-like, e.g. ``st.session_state``)."""
    state["uploaded_files"] = []
    state["upload_widget_nonce"] += 1


# ── pure UI ─────────────────────────────────────────────────────────────

def render_attachment_items(files, *, show_preview: bool = True) -> None:
    """Render the list of already-processed uploaded files.

    Args:
        files: list of dicts in the legacy ``uploaded_files`` format.
        show_preview: if True, show a text preview expander per file.
    """
    if not files:
        st.caption("未附带文件")
        return

    for meta in files:
        prefix = "📄" if meta.get("status") == "ready" else "⚠️"
        st.markdown(f"{prefix} **{meta['name']}**")
        st.caption(f"{meta['kind']} · {meta['size_label']}")
        if meta.get("warning"):
            if meta.get("status") == "ready":
                st.info(meta["warning"])
            else:
                st.error(meta["warning"])
        if show_preview and meta.get("preview_text"):
            with st.expander(f"预览 {meta['name']}", expanded=False):
                st.text(meta["preview_text"][:1200])


# ── panel controller ────────────────────────────────────────────────────

def render_upload_panel(
    state,
    *,
    supported_suffixes: list[str] | None = None,
) -> None:
    """Render the full upload panel (file_uploader + processing + attachment list).

    Args:
        state: dict-like (e.g. ``st.session_state``).  Must have keys:
               ``upload_widget_nonce``, ``processed_upload_cache``,
               ``uploaded_files``.  This function writes to those keys.
        supported_suffixes: file suffixes to accept (defaults to text/pdf/docx).
    """
    if supported_suffixes is None:
        supported_suffixes = [
            "txt", "md", "py", "json", "csv", "yaml", "yml", "toml",
            "ini", "log", "sql", "js", "ts", "html", "css", "xml",
            "pdf", "docx",
        ]

    st.subheader("📎 附件")
    widget_key = f"sidebar_uploads_{state['upload_widget_nonce']}"
    uploaded_items = st.file_uploader(
        "上传文本/PDF/DOCX",
        type=supported_suffixes,
        accept_multiple_files=True,
        key=widget_key,
        help="当前版本先支持文本、PDF、DOCX；没有上传文件时聊天行为保持不变。",
    )

    if uploaded_items:
        state["uploaded_files"] = sync_uploaded_files(
            uploaded_items,
            cache=state["processed_upload_cache"],
            on_spinner=lambda name: st.spinner(f"处理中: {name}"),
        )
    else:
        state["uploaded_files"] = []

    render_attachment_items(state["uploaded_files"], show_preview=True)

    if state["uploaded_files"] and st.button(
        "清空本轮附件", key="clear_uploaded_files", use_container_width=True
    ):
        clear_uploaded_files(state)
        st.rerun()
