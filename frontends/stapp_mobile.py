import glob
import os
import queue
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
sys.path.append(os.path.abspath(os.path.join(script_dir, "..")))

import streamlit as st

# ── Mobile password gate ───────────────────────────────────
_PASSWORD = "136168"  # ← 改这里
if not st.session_state.get("_authenticated"):
    st.title("🔒 请输入访问密码")
    _pwd = st.text_input("密码", type="password")
    if st.button("进入"):
        if _pwd == _PASSWORD:
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("密码错误")
    st.stop()
# ──────────────────────────────────────────────────────────

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
        build_upload_id,
        process_uploaded_file,
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
        build_upload_id,
        process_uploaded_file,
    )


st.set_page_config(page_title="Cowork", layout="wide")

st.markdown(
    """
<style>
/* ── Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&display=swap');

/* ── Design tokens ── */
:root {
  --bg-root: #faf8f5;
  --bg-sidebar: #f4f0e8;
  --bg-card: #fefdfb;
  --border: #e2dbcf;
  --border-focus: #c8845c;
  --text-primary: #1e1b17;
  --text-secondary: #6b6358;
  --text-muted: #9a9388;
  --accent: #c87854;
  --accent-hover: #ae6543;
  --accent-soft: #fef7f2;
  --accent-glow: rgba(200, 120, 84, 0.10);
  --shadow: 0 1px 2px rgba(60, 40, 20, 0.04);
  --shadow-card: 0 2px 8px rgba(60, 40, 20, 0.05);
  --radius-sm: 10px;
  --radius: 14px;
  --radius-lg: 18px;
  --font-display: 'Cormorant Garamond', 'Noto Serif SC', 'Source Han Serif SC', serif;
  --font-body: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ── Paper texture ── */
.stApp::before {
  content: '';
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.025'/%3E%3C/svg%3E");
  background-repeat: repeat;
  background-size: 256px 256px;
}

/* ── Global ── */
.stApp {
  background: var(--bg-root);
  color: var(--text-primary);
  font-family: var(--font-body);
}
h1, h2, h3, h4 {
  font-family: var(--font-display);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] .stCaption {
  color: var(--text-secondary) !important;
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
  min-height: 2.3rem;
  padding: 0.4rem 0.7rem;
  font-size: 0.88rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-primary);
  transition: all 0.2s ease;
  font-family: var(--font-body);
}
section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover {
  background: #f0e8db;
  border-color: #d4c4ab;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(140, 100, 60, 0.08);
}
section[data-testid="stSidebar"] button[kind="primary"] {
  background: var(--accent) !important;
  border-color: var(--accent) !important;
  color: #fff !important;
  font-weight: 600;
  border-radius: var(--radius-sm) !important;
  transition: all 0.2s ease;
}
section[data-testid="stSidebar"] button[kind="primary"]:hover {
  background: var(--accent-hover) !important;
  border-color: var(--accent-hover) !important;
  box-shadow: 0 3px 12px var(--accent-glow);
  transform: translateY(-1px);
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
  box-shadow: var(--shadow);
  font-family: var(--font-body);
  line-height: 1.65;
}
[data-testid="stChatMessage"][data-testid="stChatMessageUser"] {
  background: var(--accent-soft);
  border-color: #edd5be;
  box-shadow: var(--shadow-card);
}

/* ── Chat input ── */
[data-testid="stChatInput"] {
  background: var(--bg-root) !important;
}
[data-testid="stChatInput"] > div {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  transition: border-color 0.25s ease, box-shadow 0.25s ease;
}
/* Kill backgrounds on ALL inner children — they inherit from the container */
[data-testid="stChatInput"] > div > *,
[data-testid="stChatInput"] > div > * > * {
  background: transparent !important;
}
[data-testid="stChatInput"] > div:focus-within {
  border-color: var(--border-focus) !important;
  box-shadow: 0 0 0 4px var(--accent-glow) !important;
}
textarea[data-testid="stChatInputTextArea"] {
  background: transparent !important;
  border: none !important;
  color: var(--text-primary) !important;
  font-family: var(--font-body) !important;
  font-size: 0.95rem !important;
  line-height: 1.6 !important;
  -webkit-appearance: none !important;
  box-shadow: none !important;
}
textarea[data-testid="stChatInputTextArea"]::placeholder {
  color: var(--text-muted) !important;
  font-style: italic;
  opacity: 1 !important;
}
/* Override browser autofill — the #1 cause of cool-tinted input patches */
textarea[data-testid="stChatInputTextArea"]:-webkit-autofill,
textarea[data-testid="stChatInputTextArea"]:-webkit-autofill:hover,
textarea[data-testid="stChatInputTextArea"]:-webkit-autofill:focus {
  -webkit-box-shadow: 0 0 0 40px var(--bg-card) inset !important;
  -webkit-text-fill-color: var(--text-primary) !important;
  transition: background-color 5000s ease-in-out 0s;
}
[data-testid="stBottomBlockContainer"] {
  background: var(--bg-root) !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d8d0c3; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #b8ac99; }

/* ── Dividers ── */
section[data-testid="stSidebar"] hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 8px 4px;
}

/* ── Expand / collapsible details ── */
section[data-testid="stSidebar"] div[data-testid="stExpander"] details summary p {
  font-size: 0.88rem;
  color: var(--text-secondary) !important;
}

/* ── Code blocks ── */
pre, code {
  font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace !important;
  font-size: 0.85rem;
}
pre {
  background: #f7f4ee !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  padding: 14px 16px !important;
  line-height: 1.55 !important;
}

/* ── Links ── */
a {
  color: var(--accent) !important;
  text-decoration: none;
  transition: color 0.15s;
}
a:hover {
  color: var(--accent-hover) !important;
  text-decoration: underline;
}

/* Ensure text is selectable */
body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stChatMessageContent"],
[data-testid="stMarkdownContainer"],
.stMarkdown, .stChatMessage {
    user-select: text !important;
    -webkit-user-select: text !important;
    -moz-user-select: text !important;
    -ms-user-select: text !important;
}

/* ── Status indicator ── */
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.status-active { background: #7a9a6e; box-shadow: 0 0 6px rgba(122,154,110,0.35); }
.status-idle { background: #b8aa98; }

/* ── Stream cursor blink ── */
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
#stream-cursor { font-weight: 200; color: var(--accent); }

/* ── Jump-to-bottom button ── */
#jump-to-bottom {
  position: fixed;
  bottom: 100px;
  right: 30px;
  z-index: 9999;
  background: var(--accent);
  color: #fff;
  padding: 6px 14px;
  border-radius: 20px;
  cursor: pointer;
  display: none;
  font-size: 0.85rem;
  font-family: var(--font-body);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  transition: opacity 0.2s;
}
#jump-to-bottom:hover {
  background: var(--accent-hover);
}

/* ── Title refinement ── */
h1 {
  font-size: 2.2rem !important;
  font-style: italic;
  color: var(--text-primary) !important;
  animation: titleIn 0.8s ease both;
}
@keyframes titleIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
""",
    unsafe_allow_html=True,
)


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
    """Lazy-init the OpenAI multi-agent orchestrator (only loaded when needed)."""
    if st.session_state.orchestrator is not None:
        return st.session_state.orchestrator
    if BACKEND_KIND == "openai-agents":
        # Already running as orchestrator — reuse the main agent
        st.session_state.orchestrator = agent
        return agent
    try:
        from core.openai_agentmain import OpenAIOrchestratedAgent

        orch = OpenAIOrchestratedAgent()
        orch.llm_no = getattr(agent, "llm_no", 0)
        if not getattr(orch, "_ui_thread_started", False):
            threading.Thread(target=orch.run, daemon=True).start()
            orch._ui_thread_started = True
        st.session_state.orchestrator = orch
        return orch
    except Exception:
        return None


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

if "autonomous_enabled" not in st.session_state:
    st.session_state.autonomous_enabled = False
if "show_history" not in st.session_state:
    st.session_state.show_history = False
if "show_memory" not in st.session_state:
    st.session_state.show_memory = False
if "compact_assistant_history" not in st.session_state:
    st.session_state.compact_assistant_history = True
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "processed_upload_cache" not in st.session_state:
    st.session_state.processed_upload_cache = {}
if "upload_widget_nonce" not in st.session_state:
    st.session_state.upload_widget_nonce = 0
# Streaming / stop state
if "agent_running" not in st.session_state:
    st.session_state.agent_running = False
if "stream_started" not in st.session_state:
    st.session_state.stream_started = False
if "stop_requested" not in st.session_state:
    st.session_state.stop_requested = False
if "task_id" not in st.session_state:
    st.session_state.task_id = ""
if "partial_response" not in st.session_state:
    st.session_state.partial_response = ""
if "current_turn" not in st.session_state:
    st.session_state.current_turn = 0
if "display_queue" not in st.session_state:
    st.session_state.display_queue = None
if "scroll_event" not in st.session_state:
    st.session_state.scroll_event = 0
if "content_event" not in st.session_state:
    st.session_state.content_event = 0
if "routing_mode" not in st.session_state:
    st.session_state.routing_mode = "ask"  # "ask" | "auto" | "classic_only"
if "pending_routing" not in st.session_state:
    st.session_state.pending_routing = None  # {"prompt": ..., "task_prompt": ..., "visible": ..., "route": ...}
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = None  # lazy-init OpenAIOrchestratedAgent
if "last_submitted_input" not in st.session_state:
    st.session_state.last_submitted_input = ""
if "task_start_time" not in st.session_state:
    st.session_state.task_start_time = 0


def get_agent_state():
    """Derive explicit agent state from session_state flags.

    Returns one of:
        idle      — no task active
        running   — task queued, waiting for first output (backend thinking / tool exec)
        streaming — output chunks arriving
        stopping  — user requested stop, waiting for backend to confirm
        error     — backend reported an error
    """
    if not st.session_state.agent_running:
        return "idle"
    if st.session_state.stop_requested:
        return "stopping"
    if st.session_state.stream_started:
        return "streaming"
    return "running"


def reset_agent_state():
    """Reset all agent-related session_state flags to idle defaults."""
    st.session_state.agent_running = False
    st.session_state.stream_started = False
    st.session_state.stop_requested = False
    st.session_state.stop_requested_at = 0
    st.session_state.display_queue = None
    st.session_state.partial_response = ""
    st.session_state.current_turn = 0
    st.session_state.task_id = ""
    st.session_state.scroll_event = 0
    st.session_state.task_start_time = 0


def start_agent_task(display_queue):
    """Initialize agent state for a new task — guards against duplicate submit."""
    if st.session_state.agent_running:
        return False  # already running, reject duplicate
    st.session_state.display_queue = display_queue
    st.session_state.agent_running = True
    st.session_state.stream_started = False
    st.session_state.stop_requested = False
    st.session_state.partial_response = ""
    st.session_state.current_turn = 0
    st.session_state.scroll_event = 0
    st.session_state.content_event += 1
    st.session_state.pending_routing = None
    st.session_state.task_start_time = time.time()
    return True


def get_history_files():
    # 根据backend类型使用不同的历史目录
    if BACKEND_KIND == "openai-agents":
        hist_dir = os.path.join(script_dir, "..", "temp", "model_responses_openai")
    else:
        hist_dir = os.path.join(script_dir, "..", "temp", "model_responses")
    if not os.path.exists(hist_dir):
        return []
    files = glob.glob(os.path.join(hist_dir, "model_responses_*.txt"))
    return sorted(files, key=os.path.getmtime, reverse=True)


def get_memory_content():
    mem_dir = os.path.join(script_dir, "..", "memory")
    result = {}

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


def sync_uploaded_files(uploaded_items):
    cache = st.session_state.processed_upload_cache
    current = []
    for uploaded in uploaded_items or []:
        file_id = build_upload_id(uploaded.name, uploaded.getvalue())
        if file_id not in cache:
            with st.spinner(f"处理中: {uploaded.name}"):
                cache[file_id] = process_uploaded_file(uploaded)
        current.append(cache[file_id])
    st.session_state.uploaded_files = current


def clear_uploaded_files():
    st.session_state.uploaded_files = []
    st.session_state.upload_widget_nonce += 1


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


def render_attachment_items(show_preview=True):
    files = st.session_state.uploaded_files
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


def extract_last_user_question(filepath):
    result, err = format_restore(filepath, backend_kind=BACKEND_KIND)
    if not err and result:
        restored, _, _, fmt_type = unpack_restore_result(result)
        questions = []
        if fmt_type == "input_items":
            for item in restored or []:
                if not isinstance(item, dict) or item.get("role") != "user":
                    continue
                text = message_content_to_text(item.get("content", ""))
                text = text.strip()
                if text:
                    questions.append(text)
        else:
            questions = [line[8:] for line in restored if isinstance(line, str) and line.startswith("[USER]: ")]
        if questions:
            title = questions[-1].replace("\n", " ").strip()
            return title[:42] + ("..." if len(title) > 42 else "")
    return None


def read_history_preview(filepath, max_lines=30):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return "\n".join(f.read().splitlines()[:max_lines])
    except Exception as e:
        return f"预览失败: {e}"


def render_distill_preview(summary, filepath, fname):
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
                st.session_state[f"distill_result_{fname}"] = None
                st.rerun()
        with col_b:
            if st.button("关闭", key=f"cancel_{fname}", use_container_width=True):
                st.session_state[f"distill_result_{fname}"] = None
                st.rerun()


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
                    result, err = format_restore(filepath, backend_kind=BACKEND_KIND)
                    if result:
                        # 新格式: (data, filename, count, format_type)
                        restored, _, count, fmt_type = unpack_restore_result(result)
                        
                        # 处理不同格式
                        if fmt_type == "input_items":
                            # openai-agents新格式：restored已经是input_items列表
                            st.session_state.messages = input_items_to_messages(restored)
                            if hasattr(agent, "restore_history"):
                                agent.restore_history(restored, is_input_items=True)
                            else:
                                agent.abort()
                                agent.history = input_items_to_lines(restored)
                            if (
                                not hasattr(agent, "restore_history")
                                and hasattr(agent, "llmclient")
                                and agent.llmclient
                            ):
                                agent.llmclient.backend.history = input_items_to_backend_history(restored)
                                agent.llmclient.last_tools = ""
                        else:
                            # 旧格式：lines列表
                            st.session_state.messages = restored_lines_to_messages(restored)
                            if hasattr(agent, "restore_history"):
                                agent.restore_history(restored)
                            else:
                                agent.abort()
                                agent.history = list(restored)
                            if (
                                not hasattr(agent, "restore_history")
                                and hasattr(agent, "llmclient")
                                and agent.llmclient
                            ):
                                agent.llmclient.backend.history = restored_lines_to_backend_history(restored)
                                agent.llmclient.last_tools = ""
                        st.success(f"已恢复 {count} 轮对话，将从该对话的最后状态继续")
                        st.rerun()
                    else:
                        st.error(f"恢复失败: {err}")

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
                                agent.abort()
                                if hasattr(agent, "history"):
                                    agent.history = []
                                if (
                                    hasattr(agent, "llmclient")
                                    and agent.llmclient
                                    and hasattr(agent.llmclient, "backend")
                                    and agent.llmclient.backend
                                ):
                                    agent.llmclient.backend.history = []
                                    agent.llmclient.last_tools = ""
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
                            agent.abort()
                            if hasattr(agent, "history"):
                                agent.history = []
                            if (
                                hasattr(agent, "llmclient")
                                and agent.llmclient
                                and hasattr(agent.llmclient, "backend")
                                and agent.llmclient.backend
                            ):
                                agent.llmclient.backend.history = []
                                agent.llmclient.last_tools = ""
                            st.success(f"已删除 {fname}")
                            st.rerun()
                        else:
                            st.error(f"删除失败: {del_err}")

            summary = st.session_state.get(f"distill_result_{fname}")
            if summary:
                render_distill_preview(summary, filepath, fname)


@st.fragment
def render_memory_panel():
    st.subheader("🧠 记忆系统")
    mem_content = get_memory_content()

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
            st.caption("这里存放从历史对话中人工确认后提炼出的候选记忆，还没有自动并入 L1/L2/L3。")
            st.markdown(mem_content["history_memory_inbox.md"])


def render_upload_panel():
    st.subheader("📎 附件")
    widget_key = f"sidebar_uploads_{st.session_state.upload_widget_nonce}"
    uploaded_items = st.file_uploader(
        "上传文本/PDF/DOCX",
        type=[suffix.lstrip(".") for suffix in SUPPORTED_UPLOAD_SUFFIXES],
        accept_multiple_files=True,
        key=widget_key,
        help="当前版本先支持文本、PDF、DOCX；没有上传文件时聊天行为保持不变。",
    )
    sync_uploaded_files(uploaded_items or [])
    render_attachment_items(show_preview=True)
    if st.session_state.uploaded_files and st.button("清空本轮附件", key="clear_uploaded_files", use_container_width=True):
        clear_uploaded_files()
        st.rerun()


@st.fragment
def render_sidebar():
    # 新建对话按钮
    if st.button("➕ 新建对话", key="new_conversation", use_container_width=True, type="primary"):
        # 清空UI消息
        st.session_state.messages = []
        # 清空附件
        if "uploaded_files" in st.session_state:
            st.session_state.uploaded_files = []
        # 重置agent状态
        reset_agent_state()
        # 停止当前任务并清空后端历史
        agent.abort()
        if hasattr(agent, "history"):
            agent.history = []
        if (
            hasattr(agent, "llmclient")
            and agent.llmclient
            and hasattr(agent.llmclient, "backend")
            and agent.llmclient.backend
        ):
            agent.llmclient.backend.history = []
            agent.llmclient.last_tools = ""
        st.toast("✅ 已新建对话")
        st.rerun()
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📜 历史", key="toggle_history", use_container_width=True):
            st.session_state.show_history = not st.session_state.show_history
            st.session_state.show_memory = False
    with col2:
        if st.button("🧠 记忆", key="toggle_memory", use_container_width=True):
            st.session_state.show_memory = not st.session_state.show_memory
            st.session_state.show_history = False

    st.divider()

    if st.session_state.show_history:
        render_history_panel()
        st.divider()
    if st.session_state.show_memory:
        render_memory_panel()
        st.divider()

    render_upload_panel()
    st.checkbox(
        "压缩助手历史回复",
        key="compact_assistant_history",
        help="开启后会折叠多轮助手回复；关闭时始终展开完整历史答复。",
    )
    st.divider()

    # ── Routing mode ──
    routing_checked = st.checkbox(
        "复杂任务自动走多Agent编排",
        value=(st.session_state.routing_mode != "classic_only"),
        help="勾上：检测到复杂任务（代码/审查/搜索/执行）时，自动走多智能体编排。不勾：全部走经典路径。",
    )
    st.session_state.routing_mode = "auto" if routing_checked else "classic_only"
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
        agent.abort()
        st.session_state.stop_requested = True
        st.toast("已发送停止信号")
        st.rerun()
    if st.button("重新注入工具", use_container_width=True):
        agent.llmclient.last_tools = ""
        try:
            hist_path = os.path.join(script_dir, "..", "assets", "tool_usable_history.json")
            with open(hist_path, "r", encoding="utf-8") as f:
                tool_hist = __import__("json").load(f)
            agent.llmclient.backend.history.extend(tool_hist)
            st.toast(f"已重新注入工具，追加了 {len(tool_hist)} 条示范记录")
        except Exception as e:
            st.toast(f"注入工具示范失败: {e}")
    if st.button("🐱 桌面宠物", use_container_width=True):
        kwargs = {"creationflags": 0x08} if sys.platform == "win32" else {}
        pet_script = os.path.join(script_dir, "desktop_pet_v2.pyw")
        if not os.path.exists(pet_script):
            pet_script = os.path.join(script_dir, "desktop_pet.pyw")
        subprocess.Popen(
            [sys.executable, pet_script, "--streamlit-url", "http://localhost:8501"],
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
                # Task complete → big notification (stays until user clicks)
                summary = ctx.get("summary", "")
                _pet_req(f"notify={quote('任务完成|' + summary)}")
                _pet_req("state=idle")
            else:
                # Mid-task turn → short toast bubble (auto-dismiss 3s)
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


def fold_turns(text):
    """Return list of segments: [{'type':'text','content':...}, {'type':'fold','title':...,'content':...}]"""
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


def render_segments(segments, suffix="", key_prefix="", fold_expanded=False):
    for idx, seg in enumerate(segments):
        if seg["type"] == "fold":
            expander_seed = f"{key_prefix}_fold_{idx}" if key_prefix else str(idx)
            invisible_suffix = "".join(
                "\u200b" if bit == "0" else "\u200c"
                for byte in expander_seed.encode("utf-8", errors="ignore")
                for bit in f"{byte:08b}"
            )
            with st.expander(seg["title"] + invisible_suffix, expanded=fold_expanded):
                st.markdown(seg["content"])
        else:
            st.markdown(seg["content"] + suffix)


def should_show_live_turn(text, turn):
    if not turn:
        return False
    text = message_content_to_text(text)
    return f"Turn {turn}" not in text


def agent_backend_stream(prompt):
    display_queue = agent.put_task(prompt, source="user")
    response = ""
    current_turn = 0
    while True:
        try:
            item = display_queue.get(timeout=1)
        except queue.Empty:
            yield {"response": response, "turn": current_turn}
            continue
        # structured events: consume silently, backward compat via fallthrough
        if isinstance(item, dict) and item.get("event") in ("turn_start", "turn_end", "turn_delta", "final"):
            pass
        if isinstance(item, dict) and item.get("event") == "error":
            yield {"response": response, "turn": current_turn, "error": item.get("error", "")}
        if item.get("turn") is not None:
            try:
                current_turn = max(current_turn, int(item.get("turn") or 0))
            except Exception:
                pass
        if "next" in item:
            response = item["next"]
            yield {"response": response, "turn": current_turn}
        if "done" in item:
            yield {"response": item["done"], "turn": current_turn, "done": True}
            break


if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.msg_counter = 0
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
                    key_prefix=f"hist_{msg_id}",
                    fold_expanded=not st.session_state.compact_assistant_history,
                )
            else:
                st.markdown(message_content_to_text(msg["content"]))
    # Persistent scroll anchor — placed after all messages so JS can scroll to bottom
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
    # ── Anti-flash: force Streamlit expander content hidden when collapsed ──
    "var antiFlash=d.createElement('style');"
    "antiFlash.textContent="
    "\"[data-testid='stExpander'] details:not([open])>div{display:none!important}\";"
    "d.head.appendChild(antiFlash);"
    "var lastScrollEvent=0,lastContentEvent=0;"
    "var isNearBottom=function(){"
    "var m=d.querySelector('section.main');if(!m)return 1;"
    "return m.scrollTop+m.clientHeight>=m.scrollHeight-200;"
    "};"
    "var doScroll=function(smooth){"
    "var m=d.querySelector('section.main');if(!m)return;"
    "var b=m.querySelector('.block-container');if(!b)return;"
    "b.scrollIntoView({block:'end',behavior:smooth?'smooth':'instant'});"
    "};"
    # ── Create jump-to-bottom button (once) ──
    "var jumpBtn=d.createElement('div');"
    "jumpBtn.id='jump-to-bottom';"
    "jumpBtn.textContent='↓ 回到底部';"
    "jumpBtn.onclick=function(){doScroll(false);};"
    "d.body.appendChild(jumpBtn);"
    # ── Cursor & jump-button control ──
    "var updateCursorUI=function(){"
    "var cursor=d.querySelector('#stream-cursor');"
    "var marker=d.querySelector('#stream-marker');"
    "var active=marker&&marker.getAttribute('data-stream-active')==='1';"
    "var near=isNearBottom();"
    "if(cursor){"
    "cursor.style.opacity=(active&&near)?'1':'0';"
    "}"
    "if(jumpBtn){"
    "jumpBtn.style.display=(active&&!near)?'block':'none';"
    "}"
    "};"
    # ── User scroll listener ──
    "var scrollContainer=d.querySelector('section.main');"
    "if(scrollContainer){"
    "scrollContainer.addEventListener('scroll',function(){"
    "updateCursorUI();"
    "},{passive:true});"
    "}"
    # ── MutationObserver for stream updates ──
    "var obs=new MutationObserver(function(){"
    "var marker=d.querySelector('#stream-marker');"
    "if(marker){"
    "var active=marker.getAttribute('data-stream-active');"
    "if(active==='1'){"
    "var se=parseInt(marker.getAttribute('data-scroll-event')||'0',10);"
    "if(se!==lastScrollEvent){"
    "lastScrollEvent=se;"
    "if(isNearBottom())doScroll(false);"
    "}"
    "}"
    "}"
    "var ce=d.querySelector('#content-end');"
    "if(ce){"
    "var ev=parseInt(ce.getAttribute('data-content-event')||'0',10);"
    "if(ev!==lastContentEvent){"
    "lastContentEvent=ev;"
    "setTimeout(function(){doScroll(true);},150);"
    "}"
    "}"
    "updateCursorUI();"
    "});"
    "var target=d.querySelector('section.main .block-container')||d.body;"
    "obs.observe(target,{childList:1,subtree:1,characterData:1});"
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

def poll_agent_output():
    """Non-blocking drain the display queue. Returns True when agent signals done/stopped."""
    q = st.session_state.display_queue
    if q is None:
        return False
    task_id = st.session_state.task_id
    stop_requested = st.session_state.stop_requested

    for _ in range(20):
        try:
            item = q.get_nowait()
        except queue.Empty:
            break

        # Discard items from old tasks
        item_tid = item.get("task_id", "")
        if item_tid and item_tid != task_id:
            continue

        # ── Stop-requested path: only process terminal markers ──
        if stop_requested:
            if item.get("event") == "stopped":
                st.session_state.partial_response = item.get("next", st.session_state.partial_response)
                st.session_state.agent_running = False
                return True
            if item.get("event") == "error":
                st.session_state.partial_response = item.get("error", st.session_state.partial_response)
                st.session_state.agent_running = False
                return True
            if "done" in item:
                st.session_state.partial_response = item["done"]
                st.session_state.agent_running = False
                return True
            continue

        # ── Normal path ──
        if item.get("turn") is not None:
            try:
                st.session_state.current_turn = max(
                    st.session_state.current_turn, int(item.get("turn") or 0)
                )
            except Exception:
                pass
        if "next" in item:
            st.session_state.partial_response = item["next"]
            if not st.session_state.stream_started:
                st.session_state.stream_started = True
        if item.get("event") == "stopped":
            st.session_state.partial_response = item.get("next", st.session_state.partial_response)
            st.session_state.agent_running = False
            return True
        if item.get("event") == "error":
            st.session_state.partial_response = item.get("error", st.session_state.partial_response)
            st.session_state.agent_running = False
            return True
        if "done" in item:
            st.session_state.partial_response = item["done"]
            st.session_state.agent_running = False
            return True

    return False


if st.session_state.agent_running:
    # ── Streaming UI ──
    state = get_agent_state()
    with st.chat_message("assistant"):
        # Stop button — enabled when running (thinking/tool-exec) or streaming
        can_stop = state in ("running", "streaming")
        stop_label = {"running": "⏹ 停止", "streaming": "⏹ 停止输出", "stopping": "⏹ 正在停止…"}.get(state, "⏹ 停止输出")
        if st.button(
            stop_label,
            key="stop_generation_btn",
            disabled=not can_stop,
            type="primary" if can_stop else "secondary",
        ):
            agent.abort()
            st.session_state.stop_requested = True
            st.session_state.stop_requested_at = time.time()
            st.rerun()

        live = st.container()
        response = st.session_state.partial_response
        current_turn = st.session_state.current_turn
        cursor = "" if state == "stopping" else " ▌"

        with live:
            # ── Elapsed-aware status text ──
            elapsed = time.time() - st.session_state.get("task_start_time", time.time())
            esec = int(elapsed)

            if state == "running":
                if esec < 8:
                    st.caption("🤔 正在分析任务…")
                elif esec < 25:
                    st.caption(f"🧐 还在思考… ({esec}s)")
                elif esec < 60:
                    st.caption(f"⏳ 复杂任务，需要更多时间… ({esec}s)")
                else:
                    st.caption(f"🐢 仍在处理，可以等待或点击停止重试 ({esec}s)")
            elif state == "streaming":
                turn_tag = f"Turn {current_turn} · " if current_turn else ""
                if esec < 10:
                    st.caption(f"💭 {turn_tag}输出中…")
                elif esec < 30:
                    st.caption(f"📝 {turn_tag}处理中… ({esec}s)")
                elif esec < 90:
                    st.caption(f"☕ {turn_tag}仍在处理… ({esec}s)")
                else:
                    st.caption(f"🐢 {turn_tag}复杂任务处理中… ({esec}s)")
            elif state == "stopping" and not response:
                st.caption("⏳ 正在停止…")
            elif state == "stopping":
                st.caption("⏳ 正在停止，已保留部分输出…")

            segs = fold_turns(response)
            n_done = max(0, len(segs) - 1)
            for i in range(n_done):
                render_segments([segs[i]])
            if segs:
                if state == "streaming" and should_show_live_turn(response, current_turn):
                    # Keep classic turn marker in stream content for fold_turns parsing
                    pass
                elif state == "running" and not response:
                    # No output yet — only show status text above
                    pass
                render_segments([segs[-1]])
                # Cursor rendered as a separate HTML element so JS can control visibility
                if cursor:
                    st.markdown(
                        f'<span id="stream-cursor" style="animation: cursor-blink 1s step-end infinite;">{cursor}</span>',
                        unsafe_allow_html=True,
                    )
                st.session_state.scroll_event += 1
                st.markdown(
                    f'<div id="stream-marker" data-stream-active="1" data-scroll-event="{st.session_state.scroll_event}"></div>',
                    unsafe_allow_html=True,
                )

    # Drain queue
    done = poll_agent_output()

    # ── Force-complete after stop timeout (bypass waiting for agent confirmation) ──
    if not done and st.session_state.stop_requested:
        elapsed = time.time() - st.session_state.get("stop_requested_at", time.time())
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
        reset_agent_state()
        st.rerun()

    time.sleep(0.2)
    st.rerun()

if not st.session_state.agent_running:
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
                    orch = get_orchestrator()
                    if orch is not None:
                        dispatch_agent = orch
                        st.toast("已切换到多智能体编排模式")
                    else:
                        dispatch_agent = agent
                        st.toast("编排器不可用，使用经典模式")
                    dq = dispatch_agent.put_task(
                        pending["task_prompt"], source="user", run_id=st.session_state.task_id
                    )
                    start_agent_task(dq)
                    st.rerun()
            with c2:
                if st.button("直接执行", key="route_classic", use_container_width=True):
                    dq = agent.put_task(
                        pending["task_prompt"], source="user", run_id=st.session_state.task_id
                    )
                    start_agent_task(dq)
                    st.rerun()
            with c3:
                st.caption("Planner 会先规划再执行，适合复杂任务。直接执行跳过规划步骤，更快但缺少验证闭环。")
            # Force scroll to bottom — st.stop() may prevent MutationObserver from firing reliably
            _embed_html(
                "<script>"
                "var m=window.parent.document.querySelector('section.main');"
                "if(m){var b=m.querySelector('.block-container');"
                "if(b)b.scrollIntoView({block:'end',behavior:'instant'});}"
                "</script>",
                height=0,
            )
        st.stop()

    if prompt := st.chat_input("any task?"):
        task_prompt = build_prompt_with_attachments(prompt)
        visible_prompt = format_user_message(prompt)
        # Preserve input for potential retry after failure
        st.session_state.last_submitted_input = prompt
        st.session_state.msg_counter += 1
        st.session_state.messages.append({"role": "user", "content": visible_prompt, "id": st.session_state.msg_counter})
        st.session_state.content_event += 1
        if hasattr(agent, "_pet_req") and not prompt.startswith("/"):
            agent._pet_req("state=walk")
        with st.chat_message("user"):
            st.markdown(visible_prompt)

        # ── Complexity detection ──
        route = detect_complexity(prompt)
        task_id = str(uuid.uuid4())
        st.session_state.task_id = task_id

        if route in ("code", "review", "research", "executor") and st.session_state.routing_mode == "auto":
            # Complex task + auto mode — dispatch directly to multi-agent orchestrator
            orch = get_orchestrator()
            if orch is not None:
                dispatch_agent = orch
                st.toast("任务类型：" + {"code": "代码/重构", "review": "审查/测试", "research": "调研/搜索", "executor": "复杂任务"}.get(route, "复杂任务") + " → 多Agent编排")
            else:
                dispatch_agent = agent
                st.toast("编排器不可用，使用经典模式")
            dq = dispatch_agent.put_task(task_prompt, source="user", run_id=task_id)
            start_agent_task(dq)
            st.rerun()
        else:
            # Simple chat, routing disabled, or autonomous — dispatch directly to classic
            dq = agent.put_task(task_prompt, source="user", run_id=task_id)
            start_agent_task(dq)
            st.rerun()

if st.session_state.autonomous_enabled:
    st.markdown(
        f"""<div id="last-reply-time" style="display:none">{st.session_state.get('last_reply_time', int(time.time()))}</div>""",
        unsafe_allow_html=True,
    )
