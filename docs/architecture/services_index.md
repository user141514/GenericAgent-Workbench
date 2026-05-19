# frontends/services — 架构索引

## 性质

这些 service 是从 Streamlit 前端中抽离出的**前端侧能力服务**，用于降低 `stapp.py` 复杂度，并为未来 Vue/Electron/Rust 迁移提供边界参考。**它们不是最终后端服务层。**

## 公共约束

所有 service 强制遵守：

**允许依赖**
- Python stdlib
- `frontends.chatapp_common`（纯函数）
- `frontends.file_processor`（纯函数）
- 纯数据类型 / dataclass

**禁止依赖**
- `streamlit`（包括 `st.session_state`）
- `core.agentmain` / 任何 concrete agent class
- `core.runtime`
- `frontends.stapp` / `stapp_mobile` / `qtapp` / `stapp2`
- UI 输出（`st.success` / `st.error` / `st.toast`）
- `core.protocol` 非数据部分（channel / drainer 的实现层）

---

## 1. FileUploadService

| 文件 | `file_upload_service.py` |
|------|--------------------------|
| 职责 | 上传文件的解析、保存、去重、文本提取、预览生成 |
| 输入 | `List[Streamlit UploadedFile]` |
| 输出 | `List[UploadedFileInfo]` |
| 委托 | `frontends.file_processor` (纯函数层) |

**公开 API**

| 方法 | 说明 |
|------|------|
| `process(uploaded_items, *, on_progress=None) -> list[UploadedFileInfo]` | 批量处理上传文件 |
| `process_one(uploaded_file, *, on_progress=None) -> UploadedFileInfo` | 单文件处理 |

**数据类型**

`UploadedFileInfo` — dataclass，12 必需字段 + `metadata` dict 保留额外信息（page_count, toc_count）。`to_dict()` 返回与旧版 `process_uploaded_file()` 完全兼容的 dict。

**禁止**
- 不操作 `st.session_state.uploaded_files`
- 不操作 `st.file_uploader`
- 不渲染 UI

**调用方**
- `frontends/stapp.py` — `sync_uploaded_files()`
- `frontends/stapp_mobile.py` — `sync_uploaded_files()`

---

## 2. HistoryRestoreService

| 文件 | `history_restore_service.py` |
|------|------------------------------|
| 职责 | 历史文件发现、预览、标题提取、恢复解析 |
| 输入 | `filepath: str`, `backend_kind: str` |
| 输出 | `HistoryFileInfo` / `RestoredConversation` / `str` |
| 委托 | `frontends.chatapp_common` (format_restore / unpack_restore_result) |

**公开 API**

| 方法 | 说明 |
|------|------|
| `list_files(backend_kind="") -> list[HistoryFileInfo]` | 列出历史文件（最新在前，最多 20） |
| `preview(filepath, max_lines=30) -> str` | 读取文件前 N 行 (static) |
| `extract_title(filepath, backend_kind="") -> str` | 从历史文件中提取最后一个用户问题作为标题 |
| `restore(filepath, backend_kind="") -> RestoredConversation \| None` | 完整解析历史文件，返回结构化数据 |

**数据类型**

`HistoryFileInfo` — 文件元信息（filepath, filename, mtime, size_kb, title）。
`RestoredConversation` — 解析结果（restored 原始数据, count 轮次, fmt_type `"input_items"`/`"lines"`）。

**禁止**
- 不写入 `st.session_state.messages`
- 不写入 `agent.history` / `agent.restore_history()`
- 不渲染 UI

**调用方**
- `frontends/stapp.py` — `get_history_files()`, `extract_last_user_question()`, `read_history_preview()`, 恢复按钮分支

---

## 3. conversation_reset_service

| 文件 | `conversation_reset_service.py` |
|------|--------------------------------|
| 职责 | 清理 agent 后端对话状态（abort + 清空 history + 清空 backend history + 重置 tool cache） |
| 输入 | `agent: object` |
| 输出 | `None` |

**公开 API**

| 函数 | 说明 |
|------|------|
| `reset_agent_conversation_state(agent)` | abort + 清空 history/backend.history/last_tools，缺失属性时不报错 |

**禁止**
- 不清空 `st.session_state.messages`
- 不清空 `st.session_state.uploaded_files`
- 不渲染 UI
- 不操作 submit/put_task

**调用方**
- `frontends/stapp.py` — 新建对话按钮、删除历史按钮(提炼成功)、删除历史按钮(无提炼)

---

## 依赖方向

```
stapp.py / stapp_mobile.py   (UI + session_state + agent 写入)
  │
  ├── FileUploadService ──────→ frontends/file_processor.py
  ├── HistoryRestoreService ──→ frontends/chatapp_common.py
  └── reset_agent_conv_state ── 纯 stdlib
```

所有 service 依赖方向向下（已有模块），不反向依赖 UI。

---

## 当前状态

| Phase | Service | 状态 |
|-------|---------|------|
| S1 | FileUploadService | ✅ |
| H1 | HistoryRestoreService | ✅ |
| C1 | ConversationResetService | ✅ |
| — | Services Architecture Index | ✅ |
| D | DistillationService | 暂缓（蒸馏/记忆/删除与 UI/agent 耦合太深） |
| A | AgentSessionService | 待审计（触碰 submit/AgentInput/Drainer/stop_requested/st.rerun） |

## 下一步

Phase A0-audit：Agent 会话控制审计，只读，不改代码。对齐 stapp.py / stapp_mobile.py / stapp2.py / qtapp.py 的会话启动、轮询、停止、完成清理路径，再决定抽什么。
