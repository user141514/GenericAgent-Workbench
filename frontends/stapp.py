import glob
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from urllib.parse import quote
from urllib.request import urlopen

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
try:
    sys.stderr.reconfigure(errors="replace")
except Exception:
    pass

script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sys.path.append(os.path.abspath(os.path.join(script_dir, "..")))

import streamlit as st
try:
    from watchtower_panel import render_watchtower_panel as _render_watchtower_panel
    _WATCHTOWER_AVAILABLE = True
except Exception:
    _WATCHTOWER_AVAILABLE = False

BACKEND_KIND = os.environ.get("GA_AGENT_BACKEND", "genericagent").lower()
from core.agentmain import GeneraticAgent
from core.router_rules import RouterRules
if BACKEND_KIND == "openai-agents":
    from core.openai_agentmain import OpenAIOrchestratedAgent as BackendAgent
else:
    BackendAgent = GeneraticAgent
try:
    from frontends.chatapp_common import (
        delete_history_file,
        distill_conversation,
        format_restore,
        input_items_to_backend_history,
        input_items_to_lines,
        input_items_to_messages,
        restored_lines_to_backend_history,
        restored_lines_to_messages,
        save_distilled_memory,
        unpack_restore_result,
    )
    from frontends.file_processor import (
        SUPPORTED_UPLOAD_SUFFIXES,
        build_attachment_prompt,
    )
except ImportError:
    from chatapp_common import (
        delete_history_file,
        distill_conversation,
        format_restore,
        input_items_to_backend_history,
        input_items_to_lines,
        input_items_to_messages,
        restored_lines_to_backend_history,
        restored_lines_to_messages,
        save_distilled_memory,
        unpack_restore_result,
    )
    from file_processor import (
        SUPPORTED_UPLOAD_SUFFIXES,
        build_attachment_prompt,
    )


st.set_page_config(page_title="Cowork", layout="wide")

_css_path = os.path.join(script_dir, "assets", "stapp_theme.css")
with open(_css_path, "r", encoding="utf-8") as _f:
    _css = _f.read()
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)


@st.cache_resource
def init():
    agent = BackendAgent()
    if getattr(agent, "startup_error", None):
        st.error("⚠️ 未配置任何可用的 LLM 接口，请设置mykey.py。")
        st.stop()
    if not getattr(agent, "ready", getattr(agent, "llmclient", None) is not None):
        st.error("Startup failed.")
        st.stop()
    if not getattr(agent, "_ui_thread_started", False):
        threading.Thread(target=agent.run, daemon=True).start()
        agent._ui_thread_started = True
    return agent


agent = init()
st.caption(f"Backend: {getattr(agent, 'backend_display_name', 'genericagent')}")


def get_orchestrator():
    """Lazy-init the OpenAI multi-agent orchestrator (only loaded when needed).

    Returns (orchestrator, error_message).
    - On success: (orch, None)
    - On failure: (None, reason_string)
    """
    if st.session_state.orchestrator is not None:
        orch = st.session_state.orchestrator
        if getattr(orch, "ready", False):
            return orch, None
        err = getattr(orch, "startup_error", "") or "编排器未就绪"
        return None, err

    if BACKEND_KIND == "openai-agents":
        # Already running as orchestrator — reuse the main agent
        if getattr(agent, "ready", False):
            st.session_state.orchestrator = agent
            return agent, None
        err = getattr(agent, "startup_error", "") or "openai-agents 后端未就绪"
        return None, err

    # ── Classic backend + multi-agent checkbox: spin up orchestrator ──
    orch_startup_error = None
    try:
        from core.openai_agentmain import OpenAIOrchestratedAgent
    except ImportError as e:
        return None, f"无法导入 OpenAIOrchestratedAgent: {e}"

    try:
        orch = OpenAIOrchestratedAgent()
    except Exception as e:
        return None, f"OpenAIOrchestratedAgent 初始化失败: {e}"

    if not getattr(orch, "ready", False):
        err = getattr(orch, "startup_error", "") or "编排器初始化未完成（缺少模型配置或 openai-agents SDK）"
        return None, err

    orch.sync_from_classic_key_index(getattr(agent, "llm_no", 0))
    if not getattr(orch, "_ui_thread_started", False):
        threading.Thread(target=orch.run, daemon=True).start()
        orch._ui_thread_started = True
    st.session_state.orchestrator = orch
    return orch, None


def detect_complexity(prompt):
    """Use RouterRules to judge task complexity before dispatch.
    Returns one of: 'chat', 'code', 'review', 'research', 'executor', or None.
    """
    if not prompt or prompt.startswith("/"):
        return None
    # ── Autonomous operations always use Classic mode ──
    if prompt.startswith("[AUTO]") or prompt.startswith("[定时任务]"):
        return None
    result = RouterRules.match(prompt)
    return result.target  # 'chat' / 'code' / 'review' / 'research' / 'executor' / None

# ── Password gate (disabled: mobile not live yet) ──
# _streamlit_password = getattr(agent, "_streamlit_password", None)
# if _streamlit_password is None:
#     try:
#         from core.llmcore import mykeys
#         _streamlit_password = str(mykeys.get("streamlit_password", "")).strip()
#     except Exception:
#         _streamlit_password = ""
# if _streamlit_password:
#     if "auth_ok" not in st.session_state:
#         st.session_state.auth_ok = False
#     if not st.session_state.auth_ok:
#         st.markdown("### 🔐 GAgent Remote")
#         pwd = st.text_input("密码", type="password", placeholder="输入访问密码")
#         if st.button("登录"):
#             if pwd == _streamlit_password:
#                 st.session_state.auth_ok = True
#                 st.rerun()
#             else:
#                 st.error("密码错误")
#         st.stop()

st.title("What can I help you?")

from frontends.stapp_state import ensure_stapp_session_state
ensure_stapp_session_state(st.session_state)

# ── Routing mode indicator ──
_routing_mode = st.session_state.routing_mode
_routing_label = {
    "auto": "🤖 自动判断",
    "classic": "📋 经典模式",
    "multi_agent": "🔀 多Agent编排",
}
_routing_help = {
    "auto": "复杂任务自动走多智能体，简单对话走经典",
    "classic": "全部任务走经典单体 GenericAgent",
    "multi_agent": "全部任务强制走多智能体编排",
}
st.caption(f"{_routing_label.get(_routing_mode, '')}  |  {_routing_help.get(_routing_mode, '')}")


def get_history_files():
    from frontends.services.history_restore_service import HistoryRestoreService
    svc = HistoryRestoreService()
    return [info.filepath for info in svc.list_files(backend_kind=BACKEND_KIND)]


def get_ready_attachments():
    return [item for item in st.session_state.uploaded_files if item.get("status") == "ready"]


def build_prompt_with_attachments(prompt):
    if not prompt or str(prompt).startswith("/"):
        return prompt
    attachment_prompt = build_attachment_prompt(get_ready_attachments())
    if not attachment_prompt:
        return prompt
    return f"{prompt}\n\n{attachment_prompt}"


def format_user_message(prompt):
    ready = get_ready_attachments()
    if not ready:
        return prompt
    file_lines = "\n".join(f"- {item['name']}" for item in ready)
    return f"{prompt}\n\n已附带文件:\n{file_lines}"


from frontends.stapp_message import message_content_to_text, render_copy_reply_button


def extract_last_user_question(filepath):
    from frontends.services.history_restore_service import HistoryRestoreService
    svc = HistoryRestoreService()
    return svc.extract_title(filepath, backend_kind=BACKEND_KIND) or None


def read_history_preview(filepath, max_lines=30):
    from frontends.services.history_restore_service import HistoryRestoreService
    return HistoryRestoreService.preview(filepath, max_lines=max_lines)


def request_generation_stop():
    agent.abort()
    st.session_state.stop_requested = True
    st.session_state.stop_requested_at = time.time()


def render_generation_control_bar(key_prefix="main"):
    stopping = bool(st.session_state.get("stop_requested", False))
    c1, c2 = st.columns([4.4, 0.9])
    with c1:
        st.caption("正在停止，已收到的内容会保留。" if stopping else "正在生成回复，可以随时停止。")
    with c2:
        if st.button(
            "停止",
            key=f"{key_prefix}_stop_stream_btn",
            disabled=stopping,
            type="secondary",
            use_container_width=False,
            help="停止当前生成，并保留已经收到的部分回复。",
        ):
            request_generation_stop()
            st.rerun()
    st.chat_input("正在生成回复…", disabled=True, key=f"{key_prefix}_running_chat_input")


from frontends.stapp_history_panel import render_distill_preview


def _restore_to_agent(data, fmt_type, agent):
    """Write restored conversation into agent backend history.

    Returns the message list for ``st.session_state.messages``.
    Handles both ``input_items`` and legacy ``lines`` formats.
    """
    if fmt_type == "input_items":
        messages = input_items_to_messages(data)
        if hasattr(agent, "restore_history"):
            agent.restore_history(data, is_input_items=True)
        else:
            agent.abort()
            agent.history = input_items_to_lines(data)
        if (
            not hasattr(agent, "restore_history")
            and hasattr(agent, "llmclient")
            and agent.llmclient
        ):
            agent.llmclient.backend.history = input_items_to_backend_history(data)
            agent.llmclient.last_tools = ""
    else:
        messages = restored_lines_to_messages(data)
        if hasattr(agent, "restore_history"):
            agent.restore_history(data)
        else:
            agent.abort()
            agent.history = list(data)
        if (
            not hasattr(agent, "restore_history")
            and hasattr(agent, "llmclient")
            and agent.llmclient
        ):
            agent.llmclient.backend.history = restored_lines_to_backend_history(data)
            agent.llmclient.last_tools = ""
    return messages


@st.fragment
def render_history_panel():
    st.subheader("📜 对话历史")
    files = get_history_files()[:20]
    if not files:
        st.info("暂无历史记录")
        return

    for filepath in files:
        fname = os.path.basename(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath)).strftime("%m-%d %H:%M")
        size_kb = max(1, os.path.getsize(filepath) // 1024)
        title = extract_last_user_question(filepath)
        display_title = title or f"{mtime} ({size_kb}KB)"

        with st.container(border=True):
            with st.expander(f"📄 {display_title}", expanded=False):
                st.caption(f"{mtime} · {size_kb}KB · {fname}")
                st.text(read_history_preview(filepath))

            col_restore, col_distill, col_delete = st.columns(3)

            with col_restore:
                if st.button("恢复", key=f"restore_{fname}", use_container_width=True):
                    from frontends.services.history_restore_service import HistoryRestoreService
                    svc = HistoryRestoreService()
                    restored = svc.restore(filepath, backend_kind=BACKEND_KIND)
                    if restored:
                        data = restored.restored
                        st.session_state.messages = _restore_to_agent(
                            data, restored.fmt_type, agent
                        )
                        st.success(f"已恢复 {restored.count} 轮对话，将从该对话的最后状态继续")
                        st.rerun()
                    else:
                        st.error(f"恢复失败：文件无法解析")

            with col_distill:
                if st.button(
                    "提炼",
                    key=f"distill_btn_{fname}",
                    help="预览提炼内容，再选择写入记忆",
                    use_container_width=True,
                ):
                    summary, err = distill_conversation(filepath)
                    if summary:
                        st.session_state[f"distill_result_{fname}"] = summary
                        st.toast(f"已生成 {fname} 的提炼预览")
                    else:
                        st.warning(f"无法解析: {err}")

            with col_delete:
                if st.button(
                    "删除",
                    key=f"delete_{fname}",
                    help="提炼并写入记忆，然后删除原对话",
                    use_container_width=True,
                ):
                    summary, err = distill_conversation(filepath)
                    if summary:
                        result, save_err = save_distilled_memory(summary, filepath)
                        if result:
                            del_ok, del_err = delete_history_file(filepath)
                            if del_ok:
                                # 清理UI和后端状态
                                st.session_state.messages = []
                                st.session_state[f"distill_result_{fname}"] = None
                                from frontends.services.conversation_reset_service import reset_agent_conversation_state
                                reset_agent_conversation_state(agent)
                                st.success(f"✅ 已提炼并删除 {fname}")
                                st.toast(f"记忆已写入候选池: {summary['title'][:30]}")
                                st.rerun()
                            else:
                                st.warning(f"记忆已保存，但删除失败: {del_err}")
                        else:
                            st.error(f"保存记忆失败: {save_err}")
                    else:
                        del_ok, del_err = delete_history_file(filepath)
                        if del_ok:
                            # 清理UI和后端状态
                            st.session_state.messages = []
                            st.session_state[f"distill_result_{fname}"] = None
                            from frontends.services.conversation_reset_service import reset_agent_conversation_state
                            reset_agent_conversation_state(agent)
                            st.success(f"已删除 {fname}")
                            st.rerun()
                        else:
                            st.error(f"删除失败: {del_err}")

            summary = st.session_state.get(f"distill_result_{fname}")
            if summary:
                render_distill_preview(summary, filepath, fname)


from frontends.stapp_memory_panel import render_memory_panel, get_memory_content


from frontends.stapp_upload_panel import render_upload_panel


@st.fragment
def render_sidebar():
    # 新建对话按钮
    if st.button("➕ 新建对话", key="new_conversation", use_container_width=True, type="primary"):
        # 清空UI消息
        st.session_state.messages = []
        # 清空附件
        if "uploaded_files" in st.session_state:
            st.session_state.uploaded_files = []
        # 停止当前任务并清空后端历史
        st.session_state.agent_running = False
        st.session_state._stream_dq = None
        st.session_state._drainer = None
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        reset_agent_conversation_state(agent)
        st.toast("✅ 已新建对话")
        st.rerun()
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📜 历史", key="toggle_history", use_container_width=True):
            st.session_state.show_history = not st.session_state.show_history
            st.session_state.show_memory = False
            st.session_state.show_watchtower = False
    with col2:
        if st.button("🧠 记忆", key="toggle_memory", use_container_width=True):
            st.session_state.show_memory = not st.session_state.show_memory
            st.session_state.show_history = False
            st.session_state.show_watchtower = False
    with col3:
        if st.button("🖥️ 终端", key="toggle_watchtower", use_container_width=True, disabled=not _WATCHTOWER_AVAILABLE):
            st.session_state.show_watchtower = not st.session_state.show_watchtower
            st.session_state.show_history = False
            st.session_state.show_memory = False

    st.divider()

    if st.session_state.show_history:
        render_history_panel()
        st.divider()
    if st.session_state.show_memory:
        render_memory_panel(project_root)
        st.divider()
    if st.session_state.show_watchtower and _WATCHTOWER_AVAILABLE:
        _render_watchtower_panel()
        st.divider()

    render_upload_panel(st.session_state)
    st.checkbox(
        "压缩助手历史回复",
        key="compact_assistant_history",
        help="开启后会折叠多轮助手回复；关闭时始终展开完整历史答复。",
    )
    st.divider()

    # ── Routing mode ──
    st.caption("**路由策略**")
    _current_mode = st.session_state.routing_mode
    _policy = "auto" if _current_mode == "auto" else "select"
    _policy_idx = 0 if _policy == "auto" else 1

    routing_policy = st.radio(
        "路由策略",
        ["auto", "select"],
        index=_policy_idx,
        format_func=lambda x: "🤖 自动判断" if x == "auto" else "🔧 手动指定",
        horizontal=True,
        label_visibility="collapsed",
    )

    if routing_policy == "select":
        _sub_idx = 1 if _current_mode == "multi_agent" else 0
        routing_mode = st.radio(
            "选择后端",
            ["classic", "multi_agent"],
            index=_sub_idx,
            format_func=lambda x: (
                "📋 经典模式 (GenericAgent)" if x == "classic"
                else "🔀 多Agent编排 (Orchestrator)"
            ),
            label_visibility="collapsed",
        )
    else:
        routing_mode = "auto"

    st.session_state.routing_mode = routing_mode

    # Show orchestrator status when multi-agent might be used
    if routing_mode in ("auto", "multi_agent"):
        orch, orch_err = get_orchestrator()
        if orch is not None:
            st.success("✅ 多Agent编排已就绪")
        else:
            st.error(f"⚠️ 多Agent编排不可用: {orch_err}")
            if routing_mode == "multi_agent":
                st.caption("将回退到经典模式，直到编排器可用")
    st.divider()

    # ── Model Switcher (Key1 / Key2) ──
    current_idx = getattr(agent, "llm_no", 0)
    key_labels = getattr(agent, "get_key_labels", lambda: [])()

    if key_labels:
        st.caption(f"Current: **{agent.get_llm_name()}**")
        cols = st.columns(len(key_labels))
        for i, label in enumerate(key_labels):
            is_active = i == current_idx
            btn_label = f"Key{i + 1}" + (" ✅" if is_active else "")
            btn_help = label
            if cols[i].button(btn_label, use_container_width=True, help=btn_help, key=f"switch_key_{i}"):
                if not is_active:
                    agent.switch_to_key(i)
                    st.rerun(scope="fragment")
    else:
        st.caption(f"LLM Core: {current_idx}: {agent.get_llm_name()}", help="No multi-key config detected")
        if st.button("切换备用链路", use_container_width=True):
            agent.next_llm()
            st.rerun(scope="fragment")

    # Idle time display
    last_reply_time = st.session_state.get("last_reply_time", 0)
    if last_reply_time > 0:
        st.caption(f"空闲时间：{int(time.time()) - last_reply_time}秒")

    if st.button("强行停止任务", use_container_width=True):
        request_generation_stop()
        st.toast("已发送停止信号")
        st.rerun()
    if st.button("重新注入工具", use_container_width=True):
        agent.llmclient.last_tools = ""
        try:
            hist_path = os.path.join(script_dir, "..", "assets", "tool_usable_history.json")
            with open(hist_path, "r", encoding="utf-8") as f:
                tool_hist = __import__("json").load(f)
            # Deduplicate: skip if tool history already injected
            if not st.session_state.get("_tools_injected"):
                agent.llmclient.backend.history.extend(tool_hist)
                st.session_state._tools_injected = True
                st.toast(f"已注入工具示范，追加了 {len(tool_hist)} 条记录")
            else:
                st.toast("工具示范已存在，跳过重复注入")
        except Exception as e:
            st.toast(f"注入工具示范失败: {e}")
    if st.button("🐱 桌面宠物", use_container_width=True):
        kwargs = {"creationflags": 0x08} if sys.platform == "win32" else {}
        pet_script = os.path.join(script_dir, "desktop_pet_v2.pyw")
        if not os.path.exists(pet_script):
            pet_script = os.path.join(script_dir, "desktop_pet.pyw")
        subprocess.Popen(
            [sys.executable, pet_script],
            **kwargs
        )

        def _pet_req(q):
            def _do():
                try:
                    urlopen(f"http://127.0.0.1:41983/?{q}", timeout=2)
                except Exception:
                    pass

            threading.Thread(target=_do, daemon=True).start()

        agent._pet_req = _pet_req
        if not hasattr(agent, "_turn_end_hooks"):
            agent._turn_end_hooks = {}

        def _pet_hook(ctx):
            if ctx.get("exit_reason"):
                _pet_req("state=idle")
            parts = [f"Turn {ctx.get('turn', '?')}"]
            if ctx.get("summary"):
                parts.append(ctx["summary"])
            _pet_req(f"msg={quote(chr(10).join(parts))}")

        agent._turn_end_hooks["pet"] = _pet_hook
        st.toast("桌面宠物已启动")

    st.divider()
    if st.button("开始空闲自主行动", use_container_width=True):
        st.session_state.last_reply_time = int(time.time()) - 1800
        st.toast("已将上次回复时间设为1800秒前")
        st.rerun()

    if st.session_state.autonomous_enabled:
        if st.button("⏸️ 禁止自主行动", use_container_width=True):
            st.session_state.autonomous_enabled = False
            st.toast("⏸️ 已禁止自主行动")
            st.rerun()
        st.caption("🟢 自主行动运行中，会在你离开它30分钟后自动进行")
    else:
        if st.button("▶️ 允许自主行动", type="primary", use_container_width=True):
            st.session_state.autonomous_enabled = True
            st.toast("✅ 已允许自主行动")
            st.rerun()
        st.caption("🔴 自主行动已停止")


with st.sidebar:
    render_sidebar()


from frontends.stapp_message import (
    fold_turns,
    latest_turn_from_text,
    render_segments,
    sanitize_streaming_tail,
    should_show_live_turn,
)


# messages / msg_counter now initialised by ensure_stapp_session_state() above
# assign stable ids to legacy messages (from prior sessions)
for m in st.session_state.messages:
    if "id" not in m:
        st.session_state.msg_counter += 1
        m["id"] = st.session_state.msg_counter
for msg_idx, msg in enumerate(st.session_state.messages):
    msg_id = msg.get("id", msg_idx)
    with st.chat_message(msg["role"]):
        slot = st.empty()
        with slot.container():
            if msg["role"] == "assistant":
                render_segments(
                    fold_turns(msg["content"]),
                    fold_expanded=not st.session_state.compact_assistant_history,
                )
                render_copy_reply_button(msg["content"], key=f"hist_{msg_id}")
            else:
                st.markdown(message_content_to_text(msg["content"]))
# Persistent scroll anchor — placed once after all messages so JS can scroll to bottom
st.markdown(
    f'<div id="content-end" data-content-event="{st.session_state.content_event}"></div>',
    unsafe_allow_html=True,
)

try:
    from streamlit import iframe as _st_iframe

    _embed_html = lambda html, **kw: _st_iframe(
        html, **{k: max(v, 1) if isinstance(v, int) else v for k, v in kw.items()}
    )
except (ImportError, AttributeError):
    from streamlit.components.v1 import html as _embed_html

_js_scroll_fix = (
    "!function(){var p=window.parent;if(p.__sfx)return;p.__sfx=1;"
    "var d=p.document;"
    "var lastContentEvent=0;"
    "var isNearBottom=function(){"
    "var m=d.querySelector('section.main');if(!m)return 1;"
    "return m.scrollTop+m.clientHeight>=m.scrollHeight-80;"
    "};"
    "var doScroll=function(smooth){"
    "var m=d.querySelector('section.main');if(!m)return;"
    "var b=m.querySelector('.block-container');if(!b)return;"
    "b.scrollIntoView({block:'end',behavior:smooth?'smooth':'instant'});"
    "};"
    "var jumpBtn=d.createElement('div');"
    "jumpBtn.id='jump-to-bottom';"
    "jumpBtn.textContent='↓ 回到底部';"
    "jumpBtn.onclick=function(){doScroll(false);};"
    "d.body.appendChild(jumpBtn);"
    "var updateJumpBtn=function(){"
    "if(jumpBtn)jumpBtn.style.display=isNearBottom()?'none':'block';"
    "};"
    "var sc=d.querySelector('section.main');"
    "if(sc)sc.addEventListener('scroll',updateJumpBtn,{passive:true});"
    "var obs=new MutationObserver(function(){"
    "var ce=d.querySelector('#content-end');"
    "if(ce){"
    "var ev=parseInt(ce.getAttribute('data-content-event')||'0',10);"
    "if(ev!==lastContentEvent){"
    "lastContentEvent=ev;"
    "if(isNearBottom()){setTimeout(function(){doScroll(true);},150);}"
    "}"
    "}"
    "updateJumpBtn();"
    "});"
    "var target=d.querySelector('section.main .block-container')||d.body;"
    "obs.observe(target,{childList:1,subtree:1});"
    "}()"
)
_js_ime_fix = (
    ""
    if os.name == "nt"
    else "!function(){if(window.parent.__imeFix)return;window.parent.__imeFix=1;"
    "var d=window.parent.document,c=0;"
    "d.addEventListener('compositionstart',()=>c=1,!0);"
    "d.addEventListener('compositionend',()=>c=0,!0);"
    "function f(){d.querySelectorAll('textarea[data-testid=stChatInputTextArea]')"
    ".forEach(t=>{t.__imeFix||(t.__imeFix=1,t.addEventListener('keydown',e=>{"
    "e.key==='Enter'&&!e.shiftKey&&(e.isComposing||c||e.keyCode===229)&&"
    "(e.stopImmediatePropagation(),e.preventDefault())},!0))})}"
    "f();new MutationObserver(f).observe(d.body,{childList:1,subtree:1})}()"
)
_embed_html(f"<script>{_js_scroll_fix};{_js_ime_fix}</script>", height=0)

def start_agent_task(prompt, dispatch_agent):
    """Submit a task via AgentBackend protocol and init the output drainer."""
    from core.agent_factory import ensure_agent_backend
    from core.protocol.input import AgentInput
    from core.protocol.drain import AgentOutputDrainer

    st.session_state.partial_response = ""
    st.session_state.current_turn = 0
    st.session_state.stream_started = False
    st.session_state.stop_requested = False
    st.session_state.stop_requested_at = 0.0

    backend = ensure_agent_backend(dispatch_agent)
    channel = backend.submit(AgentInput(query=prompt))
    drainer = AgentOutputDrainer(channel, stop_requested=False)
    st.session_state._drainer = drainer
    st.session_state.agent_running = True


def poll_agent_output():
    """Non-blocking drain via AgentOutputDrainer. Returns True when done/stopped/error."""
    d = st.session_state.get("_drainer")
    if d is None:
        return False
    # Sync stop_requested flag before collecting
    d.stop_requested = st.session_state.stop_requested
    d.collect(max_items=20)
    st.session_state.partial_response = d.full_text
    st.session_state.current_turn = max(d.current_turn, latest_turn_from_text(d.full_text))
    if d.full_text and not st.session_state.stream_started:
        st.session_state.stream_started = True
    return d.is_terminal


# ── Idle state: routing suggestion or chat input ──
if not st.session_state.get("agent_running", False):
    # ── Routing suggestion UI (shown after complexity detection, before dispatch) ──
    pending = st.session_state.pending_routing
    if pending is not None:
        route_label = {"code": "代码/重构", "review": "审查/测试", "research": "调研/搜索", "executor": "复杂任务"}
        route_hint = route_label.get(pending["route"], "复杂任务")
        with st.chat_message("assistant"):
            st.info(f"**任务类型判断：{route_hint}** — 这类任务用多智能体编排（规划 → 执行 → 验证）效果更好。")
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                if st.button("用 Planner 编排", key="route_planner", type="primary", use_container_width=True):
                    if st.session_state.agent_running:
                        st.toast("已有任务在运行，请等待完成后再操作")
                    else:
                        orch, _orch_err = get_orchestrator()
                        dispatch_agent = orch if orch is not None else agent
                        if orch is None:
                            st.toast("编排器不可用，使用经典模式")
                        st.session_state.pending_routing = None
                        start_agent_task(pending["task_prompt"], dispatch_agent)
                        st.rerun()
            with c2:
                if st.button("直接执行", key="route_classic", use_container_width=True):
                    if st.session_state.agent_running:
                        st.toast("已有任务在运行，请等待完成后再操作")
                    else:
                        st.session_state.pending_routing = None
                        start_agent_task(pending["task_prompt"], agent)
                        st.rerun()
            with c3:
                st.caption("Planner 会先规划再执行，适合复杂任务。直接执行跳过规划步骤，更快但缺少验证闭环。")
        st.stop()

    prompt = st.chat_input("any task?")
    if prompt:
        task_prompt = build_prompt_with_attachments(prompt)
        visible_prompt = format_user_message(prompt)
        st.session_state.last_submitted_input = prompt
        st.session_state.msg_counter += 1
        st.session_state.messages.append({"role": "user", "content": visible_prompt, "id": st.session_state.msg_counter})
        st.session_state.content_event += 1
        if hasattr(agent, "_pet_req") and not prompt.startswith("/"):
            agent._pet_req("state=walk")
        with st.chat_message("user"):
            st.markdown(visible_prompt)

        # ── Complexity detection & dispatch ──
        route = detect_complexity(prompt)
        routing_mode = st.session_state.routing_mode
        route_labels = {"code": "代码/重构", "review": "审查/测试", "research": "调研/搜索", "executor": "复杂任务"}

        use_orchestrator = False
        dispatch_reason = ""
        if routing_mode == "multi_agent":
            use_orchestrator = True
            dispatch_reason = "手动指定 → 多Agent编排"
        elif routing_mode == "auto" and route in ("code", "review", "research", "executor"):
            use_orchestrator = True
            dispatch_reason = f"任务类型：{route_labels.get(route, '复杂任务')} → 多Agent编排"
        elif routing_mode == "ask" and route in ("code", "review", "research", "executor"):
            # Ask mode + complex task — show routing choice UI
            st.session_state.pending_routing = {
                "route": route,
                "task_prompt": task_prompt,
            }
            st.rerun()
        else:
            dispatch_reason = "经典模式" if routing_mode == "classic" else "简单对话 → 经典"

        if use_orchestrator:
            orch, orch_error = get_orchestrator()
            if orch is not None:
                dispatch_agent = orch
                st.toast(dispatch_reason, icon="🤖")
            else:
                dispatch_agent = agent
                st.toast(f"⚠️ 编排器不可用：{orch_error}\n已回退经典模式", icon="⚠️")
        else:
            dispatch_agent = agent

        # Reset streaming state for new task
        start_agent_task(task_prompt, dispatch_agent)
        st.rerun()

# ── Streaming state: poll-based rendering (non-blocking, stop button works) ──
if st.session_state.get("agent_running", False):
    with st.chat_message("assistant"):
        response = st.session_state.partial_response
        current_turn = max(st.session_state.current_turn, latest_turn_from_text(response))
        cursor = "" if st.session_state.stop_requested else " ▌"

        if response:
            segs = fold_turns(response)
            n_done = max(0, len(segs) - 1)
            for i in range(n_done):
                render_segments([segs[i]])
            if segs:
                if should_show_live_turn(response, current_turn):
                    st.caption(f"LLM Running (Turn {current_turn}) ...")
                segs[-1]["content"] = sanitize_streaming_tail(segs[-1]["content"])
                render_segments([segs[-1]], suffix=cursor)
        elif st.session_state.stream_started:
            # Stream started but empty response (should not normally happen)
            pass
        else:
            # Pre-streaming: agent is thinking
            st.caption("正在分析任务…")

    render_generation_control_bar(key_prefix="main")

    # Drain queue
    done = poll_agent_output()

    # Force-complete after stop timeout
    if not done and st.session_state.stop_requested:
        elapsed = time.time() - st.session_state.stop_requested_at
        if elapsed > 1.5:
            done = True

    if done:
        final_response = st.session_state.partial_response
        if not final_response:
            final_response = "(已停止)"
        st.session_state.msg_counter += 1
        st.session_state.messages.append({"role": "assistant", "content": final_response, "id": st.session_state.msg_counter})
        st.session_state.content_event += 1
        st.session_state.last_reply_time = int(time.time())
        # Reset streaming state
        st.session_state.agent_running = False
        st.session_state._stream_dq = None
        st.session_state._drainer = None
        st.session_state.partial_response = ""
        st.session_state.current_turn = 0
        st.session_state.stream_started = False
        st.session_state.stop_requested = False
        st.session_state.stop_requested_at = 0.0
        st.rerun()

    time.sleep(0.2)
    st.rerun()

if st.session_state.autonomous_enabled:
    st.markdown(
        f"""<div id="last-reply-time" style="display:none">{st.session_state.get('last_reply_time', int(time.time()))}</div>""",
        unsafe_allow_html=True,
    )
