"""
CLI Watchtower — Streamlit panel for monitoring console windows.
Provides: window enumeration, screenshot display, activation, text input injection.
"""
import os
import sys
import time

import streamlit as st

# Ensure core/ is on path
_CORE_DIR = os.path.join(os.path.dirname(__file__), "..", "core")
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)


def _lazy_import():
    """Import win32_console lazily; return None if unavailable."""
    try:
        import win32_console
        return win32_console
    except Exception as e:
        return f"ImportError: {e}"


@st.fragment(run_every=None)
def render_watchtower_panel():
    """Render the CLI watchtower panel (window list + screenshot + input)."""
    st.subheader("🖥️ 终端监控")

    w32 = _lazy_import()
    if isinstance(w32, str) or w32 is None:
        st.error(f"win32_console 模块不可用: {w32}")
        st.caption("需要：pywin32 + Pillow + psutil")
        return

    # ── Enumerate windows ──
    try:
        windows = w32.enumerate_console_windows()
    except Exception as e:
        st.error(f"枚举窗口失败: {e}")
        return

    if not windows:
        st.warning("未找到任何 ConsoleWindowClass 窗口")
        if st.button("🔄 刷新", key="wt_refresh_empty", use_container_width=True):
            st.rerun(scope="fragment")
        return

    # ── Window selector ──
    def _label(w):
        title = w["title"]
        if len(title) > 50:
            title = title[:47] + "..."
        return f"{w['proc_name']} | {title} (PID {w['pid']})"

    labels = [_label(w) for w in windows]
    selected_idx = st.selectbox(
        "选择窗口",
        range(len(windows)),
        format_func=lambda i: labels[i],
        key="wt_window_select",
        label_visibility="collapsed",
    )
    selected = windows[selected_idx]
    hwnd = selected["hwnd"]

    # ── Action row ──
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 刷新", key="wt_refresh", use_container_width=True):
            st.rerun(scope="fragment")
    with col2:
        if st.button("⬆️ 唤起", key="wt_activate", use_container_width=True):
            ok = w32.activate_window(hwnd)
            st.toast("✅ 已激活" if ok else "❌ 激活失败")
    with col3:
        if st.button("🛑 Ctrl+C", key="wt_ctrlc", use_container_width=True):
            w32.send_ctrl_c(hwnd)
            st.toast("已发送 Ctrl+C")

    # ── Screenshot ──
    b64 = w32.capture_window_image_b64(hwnd)
    if b64:
        st.image(
            f"data:image/png;base64,{b64}",
            use_container_width=True,
            caption=f"HWND={hwnd}  |  {selected['title'][:60]}",
        )
    else:
        st.info("📷 截图失败（窗口可能已最小化或关闭）")

    # ── Input row ──
    st.divider()
    st.caption("📨 发送输入到该终端")

    input_text = st.text_input(
        "输入内容",
        key="wt_input_text",
        placeholder="输入命令或文本，回车发送...",
        label_visibility="collapsed",
    )

    sc1, sc2, sc3 = st.columns([2, 1, 1])
    with sc1:
        send_enter = st.button("▶ 发送 + Enter", key="wt_send_enter", use_container_width=True, type="primary")
    with sc2:
        send_only = st.button("发送", key="wt_send_only", use_container_width=True)
    with sc3:
        send_enter_only = st.button("⏎", key="wt_enter_only", use_container_width=True, help="只发回车")

    if send_enter and input_text:
        w32.activate_window(hwnd)
        time.sleep(0.05)
        w32.send_text_to_console(hwnd, input_text)
        w32.send_enter_to_console(hwnd)
        st.toast(f"✅ 已发送: {input_text[:30]}")
    elif send_only and input_text:
        w32.activate_window(hwnd)
        time.sleep(0.05)
        w32.send_text_to_console(hwnd, input_text)
        st.toast("✅ 已发送（无回车）")
    elif send_enter_only:
        w32.activate_window(hwnd)
        w32.send_enter_to_console(hwnd)
        st.toast("✅ 已发送回车")