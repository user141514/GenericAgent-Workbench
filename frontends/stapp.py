import glob
import os
import queue
import re
import subprocess
import sys
import threading
import time
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

BACKEND_KIND = os.environ.get("GA_AGENT_BACKEND", "genericagent").lower()
if BACKEND_KIND == "openai-agents":
    from core.openai_agentmain import OpenAIOrchestratedAgent as BackendAgent
else:
    from core.agentmain import GeneraticAgent as BackendAgent
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
section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
    min-height: 2.4rem;
    padding: 0.35rem 0.6rem;
    font-size: 0.95rem;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] details summary p {
    font-size: 0.98rem;
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
    else:
        threading.Thread(target=agent.run, daemon=True).start()
    return agent


@st.cache_resource
def init():
    agent = BackendAgent()
    if getattr(agent, "startup_error", None):
        st.error(agent.startup_error)
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

st.title("🖥️ Cowork")

if "autonomous_enabled" not in st.session_state:
    st.session_state.autonomous_enabled = False
if "show_history" not in st.session_state:
    st.session_state.show_history = False
if "show_memory" not in st.session_state:
    st.session_state.show_memory = False
if "compact_assistant_history" not in st.session_state:
    st.session_state.compact_assistant_history = False
if "uploaded_files" not in st.session_state:
    st.session_state.uploaded_files = []
if "processed_upload_cache" not in st.session_state:
    st.session_state.processed_upload_cache = {}
if "upload_widget_nonce" not in st.session_state:
    st.session_state.upload_widget_nonce = 0


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

    current_idx = getattr(agent, "llm_no", 0)
    st.caption(f"LLM Core: {current_idx}: {agent.get_llm_name()}", help="点击切换备用链路")
    last_reply_time = st.session_state.get("last_reply_time", 0)
    if last_reply_time > 0:
        st.caption(f"空闲时间：{int(time.time()) - last_reply_time}秒", help="当超过30分钟未收到回复时，系统会自动任务")

    if st.button("切换备用链路", use_container_width=True):
        agent.next_llm()
        st.rerun(scope="fragment")
    if st.button("强行停止任务", use_container_width=True):
        agent.abort()
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
        subprocess.Popen([sys.executable, pet_script], **kwargs)

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
            parts = [f"Turn {ctx.get('turn', '?')}"]
            if ctx.get("summary"):
                parts.append(ctx["summary"])
            if ctx.get("exit_reason"):
                parts.append("任务已完成")
            _pet_req(f"msg={quote(chr(10).join(parts))}")
            if ctx.get("exit_reason"):
                _pet_req("state=idle")

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
for msg_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        slot = st.empty()
        with slot.container():
            if msg["role"] == "assistant":
                render_segments(
                    fold_turns(msg["content"]),
                    key_prefix=f"hist_{msg_idx}",
                    fold_expanded=not st.session_state.compact_assistant_history,
                )
            else:
                st.markdown(message_content_to_text(msg["content"]))

try:
    from streamlit import iframe as _st_iframe

    _embed_html = lambda html, **kw: _st_iframe(
        html, **{k: max(v, 1) if isinstance(v, int) else v for k, v in kw.items()}
    )
except (ImportError, AttributeError):
    from streamlit.components.v1 import html as _embed_html

_js_scroll_fix = (
    "!function(){var p=window.parent;if(p.__sfx)return;p.__sfx=1;"
    "var d=p.document;setInterval(function(){"
    "var m=d.querySelector('section.main');if(!m)return;"
    "var b=m.querySelector('.block-container');if(!b)return;"
    "if(m.scrollHeight>b.scrollHeight+150){"
    "m.style.overflow='hidden';void m.offsetHeight;m.style.overflow=''}"
    "},3000)}()"
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

if prompt := st.chat_input("any task?"):
    task_prompt = build_prompt_with_attachments(prompt)
    visible_prompt = format_user_message(prompt)
    st.session_state.messages.append({"role": "user", "content": visible_prompt})
    if hasattr(agent, "_pet_req") and not prompt.startswith("/"):
        agent._pet_req("state=walk")
    with st.chat_message("user"):
        st.markdown(visible_prompt)

    with st.chat_message("assistant"):
        frozen = 0
        live = st.empty()
        response = ""
        current_turn = 0
        cursor = " ▌"
        for payload in agent_backend_stream(task_prompt):
            response = payload["response"]
            current_turn = payload.get("turn", current_turn)
            segs = fold_turns(response)
            n_done = max(0, len(segs) - 1)
            while frozen < n_done:
                with live.container():
                    render_segments([segs[frozen]])
                live = st.empty()
                frozen += 1
            with live.container():
                if should_show_live_turn(response, current_turn):
                    st.caption(f"LLM Running (Turn {current_turn}) ...")
                render_segments([segs[-1]], suffix=cursor)
        segs = fold_turns(response)
        for i in range(frozen, len(segs)):
            with live.container():
                if i == len(segs) - 1 and should_show_live_turn(response, current_turn):
                    st.caption(f"LLM Running (Turn {current_turn}) ...")
                render_segments([segs[i]])
            if i < len(segs) - 1:
                live = st.empty()
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.session_state.last_reply_time = int(time.time())

if st.session_state.autonomous_enabled:
    st.markdown(
        f"""<div id="last-reply-time" style="display:none">{st.session_state.get('last_reply_time', int(time.time()))}</div>""",
        unsafe_allow_html=True,
    )
