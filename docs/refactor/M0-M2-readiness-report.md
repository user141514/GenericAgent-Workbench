# Memory System Refactor Readiness Report

> **Phase:** M0–M2 (Readiness Assessment + Decision + Canonical Design)
> **Date:** 2026-05-05
> **Status:** No runtime changes. Decisions only.

---

## 1. Refactor Rules Loaded

来源文件已全部读取并交叉验证：

| # | 文档 | 状态 |
|---|------|------|
| 1 | `docs/refactor/memory-system-audit.md` | 已读，与代码逐项核对 |
| 2 | `docs/refactor/rebuild-decision.md` | 已读，决策框架已确认 |
| 3 | `docs/refactor/canonical-context-pipeline.md` | 已读，作为 target design |
| 4 | `docs/refactor/deprecated-paths.md` | 已读，deprecation 列表已核对 |
| 5 | `docs/refactor/test-matrix.md` | 已读，test coverage 已核对 |

治理规则：
- **Phase 1 (M0-M2)**: 只做 inventory + decision + design，不许改 runtime
- **Phase 2 (M3-M5)**: 建立 canonical path（新代码，不删旧）
- **Phase 3 (M6-M7)**: 双轨并行验证 → 迁移
- **Phase 4 (M8+)**: 删除 deprecated 路径

---

## 2. Current Memory Sources Inventory

### 2.1 静态模板

| Source | 加载方式 | 位置 |
|--------|----------|------|
| `sys_prompt.txt` / `sys_prompt_en.txt` | `agentmain.py:76` `get_system_prompt()` | `assets/` |
| `insight_fixed_structure.txt` | `legacy_global.py:99` `build_legacy_memory_block()` | `assets/` |
| `global_mem_insight_template.txt` | `agentmain.py:55-56` (bootstrap) | `assets/` |
| `tools_schema.json` / `_cn.json` | `agentmain.py:41` (module level) | `assets/` |
| `CAPABILITY_BRIEF` | `openai_agentmain.py:71` (hardcoded) | Python literal |
| `SUMMARY_PROTOCOL_ZH` / `_EN` | `openai_agentmain.py:80-89` (hardcoded) | Python literal |
| `THINKING_PROMPT_ZH` / `_EN` | `llmcore.py:1241-1248` (hardcoded) | Python literal |

### 2.2 Memory Files (L1/L2/Inbox)

**5 条独立 L1/L2 读路径（已验证）：**

| # | 模块 | 函数 | 行号 | 格式 |
|---|------|------|------|------|
| 1 | `core/memory/legacy_global.py` | `read_legacy_l1_l2()` | 48,59 | Raw text (dict) |
| 2 | `core/memory/legacy_global.py` | `build_legacy_memory_block()` | 93,115 | 套 `insight_fixed_structure.txt` 模板 |
| 3 | `core/memory/reader.py` | `read_global_memory()` | 24,34 | `{source, content, chars}` dict |
| 4 | `core/memory/maintenance.py` | `build_scoped_memory_context()` | 144 | 关键词过滤段落 |
| 5 | `core/context/memory_reader.py` | `MemoryReader.read_global_memory()` | 89,90 | `{l1: str, l2: str}` dict |

**Inbox — `memory/history_memory_inbox.md`：**
- `chatapp_common.py::save_distilled_memory()` — dedup check + append
- `maintenance.py::dedup_inbox()` — 去重
- `maintenance.py::archive_inbox_to_structured()` — 归档到 SQLite

### 2.3 Skills / SOP (L3)

- ~17 个 `.md` / `.py` 文件在 `memory/` 下
- 通过 `skill_prompt_injector.py::SkillSelector` 读取
- 同时被 `insight_fixed_structure.txt` 引用（双重发现路径）

### 2.4 结构化记忆 (SQLite FTS5)

- `memory/catalog.sqlite`（可选）
- 读：`store.py::MemoryStore.search_evidence_chunks()` (364)
- 写：`store.py::add_memory_item/candidate/evidence_chunk/event()`
- 写入受 `MemoryWriteGate` 控制

### 2.5 Raw Session History

- `memory/L4_raw_sessions/` — 被 `insight_fixed_structure.txt` 引用

### 2.6 对话日志

- `temp/model_responses/model_responses_*.txt` (Classic)
- `temp/model_responses_openai/model_responses_*.txt` (OpenAI)
- 读：`chatapp_common.py::format_restore()` (286)

### 2.7 Context Runtime（已构建，未接入）

已验证 `core/context/` 目录已有：

| 模块 | 职责 | 状态 |
|------|------|------|
| `memory_reader.py::MemoryReader` | 统一 L1/L2 + 结构化 + session 读 | **已构建**，gated by `GA_CONTEXT_RUNTIME_ENABLED` |
| `context_builder.py::ContextBuilder` | 组装 `ContextPacket` | **已构建**，gated by same |
| `workspace_probe.py::WorkspaceProbe` | 工作区检测 | **已构建** |
| `project_identity.py::detect_project()` | 项目识别 | **已构建** |
| `runtime_identity.py::detect_runtime()` | 运行时识别 | **已构建** |
| `session_store.py::SessionStore` | Session/task 持久化 | **已构建** |
| `recent_turns.py` | Recent conversation block | **已构建 + 已接入 OpenAI path** |
| `session_dump.py` | Session dump/restore | **已构建** |

**关键发现：`MemoryReader` 和 `ContextBuilder` 已实现完整，但未接入任何 runtime 路径。所有现有上下文注入仍走旧 5 条 L1/L2 读路径。**

### 2.8 Summary Statistics

| Metric | Count |
|--------|-------|
| Context source types | 8（新增 context runtime 未计入 audit） |
| L1/L2 read paths | 5（audit 确认一致） |
| Classic injection points | 6（audit 报 5，代码核实增加 working_memory feishu 分支） |
| OpenAI injection points | 11（audit 报 10，核实代码为 11） |
| Write paths | 11 |
| Existing canonical path modules (not yet wired) | 6 |
---

## 3. Current Injection Points Inventory

### 3.1 Classic Path

```
agentmain.py:71  get_system_prompt()
    → sys_prompt.txt + date + get_global_memory()
    → get_global_memory() = core/memory/legacy_global.py::build_legacy_memory_block()
    → 包含 insight_fixed_structure.txt 模板 + L1 + L2
    → 缓存 60s，无写入触发失效

agentmain.py:469  extra_sys_prompt
    → getattr(self.llmclient.backend, 'extra_sys_prompt', '')

agentmain.py:487  _build_recent_context(self.history, raw_query)
    → [RECENT CONVERSATION CONTEXT] block
    → 仅在 history 非空时注入

ga.py:657       _get_anchor_prompt()
    → [WORKING MEMORY] block
    → 仅在 feishu source 执行

ga.py:727       turn_end_callback()（每 10 轮）
    → get_global_memory() 重新注入
    → 周期性 L1/L2 刷新

agent_loop.py:359  agent_runner_loop()
    → messages[0] = system prompt
    → messages[1] = user input (含 recent context)
```

### 3.2 OpenAI Path（11 个注入点）

全部在 `openai_agentmain.py::_run_task_async()` 中（line ~2456-2784），以 `inputs.append({"role": "user", ...})` 方式添加：

| # | Block | Line | 触发条件 | Role 标记 |
|---|-------|------|----------|-----------|
| 1 | Working memory (last 20 history) | 2457 | 始终 | `role: user` |
| 2 | Context runtime packet | 2463 | `GA_CONTEXT_RUNTIME_ENABLED` | `role: user` |
| 3 | Recent conversation block (5 turns, 6000c) | 2478 | 始终 | `role: user` |
| 4 | Legacy L1/L2 memory | 2492 | `GA_OPENAI_LEGACY_MEMORY` (default on) | `role: user` |
| 5 | Route hint | 2438 | 路由匹配时 | `role: user` |
| 6 | Answer quality context | 2514 | code/review/research | `role: user` |
| 7 | Read prefetch | 2540 | 配置开启时 | `role: user` |
| 8 | Ambiguous follow-up guard | 2783 | ambiguous + no recent | `role: user` |
| 9 | Skill SOP context | 2700+ | planner agent | `role: user` |
| 10 | Skill activation policy | 2720+ | skill 匹配时 | `role: user` |
| 11 | Raw user query | 2784 | 始终 | `role: user`（最后一条） |

**Critical issue (F6): 全部使用 `role: user`，模型无法区分注入上下文与真实用户输入。**

### 3.3 LLM Core Wrappers

| Wrapper | 行号 | System prompt 注入方式 |
|---------|------|----------------------|
| `ClaudeSession.raw_ask()` | 729 | `payload["system"] = self.system` |
| `NativeClaudeSession.raw_ask()` | 823 | `payload["system"]` 或首条消息前 |
| `LLMSession.make_messages()` | 774 | `{"role": "system", "content": ...}` |
| `NativeOAISession.raw_ask()` | 911 | `{"role": "system", "content": ...}` |

---

## 4. Current Write Paths Inventory

| # | Writer | 目标 | 并发安全 |
|---|--------|------|----------|
| 1 | `agentmain.py:50-56` (module init) | `global_mem.txt`, `global_mem_insight.txt` (bootstrap) | — (只写一次) |
| 2 | `chatapp_common.py:592` `save_distilled_memory()` | `history_memory_inbox.md` (append) | **无锁** |
| 3 | `distillation.py:235` `write_distillation_candidate()` | `history_memory_inbox.md` (append) | **无锁** |
| 4 | `maintenance.py:30` `dedup_inbox()` | `history_memory_inbox.md` (rewrite) | 无锁 |
| 5 | `maintenance.py:222` `archive_inbox_to_structured()` | `catalog.sqlite` + truncate inbox | SQLite 事务（安全） |
| 6 | `ga.py:641` `do_start_long_term_update()` | L1/L2 via agent tool call | Agent-gated |
| 7 | `ga.py:162` `log_memory_access()` | `memory/file_access_stats.json` | 无锁 |
| 8 | `store.py::MemoryStore` 系列 | `catalog.sqlite` | SQLite 事务（安全） |
| 9 | `chatapp_common.py::_log_exchange()` | `model_responses*.txt` | 单线程 Streamlit |
| 10 | `session_store.py::SessionStore` | session state db | SQLite 事务 |

**Race condition risks:** #2, #3（两个 inbox 写入者均有 read-check-write 竞态）。

---

## 5. Failure Pattern Diagnosis

### F1. Duplicate L1/L2 Read Paths [CRITICAL — 已验证]

5 条独立读路径经代码核实，位置与 audit 一致。每条路径的格式化策略不同：
- 路径 1,3,5: 返回 raw text / dict
- 路径 2: 套模板 wrapper
- 路径 4: 关键词过滤段落

**Impact:** Classic 和 OpenAI path 看到不同格式的 L1/L2 内存。更改 L1/L2 结构需在 5 个位置同步修改。

### F2. System Prompt Cache Staleness [MEDIUM — 已验证]

`agentmain.py:74` — 60s TTL 缓存，无写入触发失效。与 audit 一致。

### F3. Assistant Output as Executed Fact [HIGH — 新增发现]

Audit 列出的 `ga.py:669` (`_safe_summary()`) 现在已加入 `_safe_summary()` 幻觉检测（本次对话已改），但仅在 turn≤2 时生效。长期运行下幻觉 summary 仍可进入 history。

**新增发现：** OpenAI path 的 `openai_agentmain.py:2969` `_extract_summary_line()` 没有幻觉检测。

### F4. Unbounded Context Growth [MEDIUM — 已验证]

| 位置 | 问题 |
|------|------|
| `openai_agentmain.py:238` `_working_memory_message()` | 20 条历史，无单条 char 预算 |
| `ga.py:659` `_get_anchor_prompt()` | 20 条，无 char 预算 |
| `context/recent_turns.py:117` | 6000 chars 总预算，无 per-turn cap |
| `chatapp_common.py:592` | Inbox append-only，无大小限制 |

### F5. Race Conditions in Inbox Writes [MEDIUM — 已验证]

`save_distilled_memory()` 和 `write_distillation_candidate()` 均无文件锁。与 audit 一致。

### F6. Context Injection Confusion in OpenAI Path [HIGH — 已验证]

11 个 `{"role": "user"}` entries 无结构区分。模型无法识别哪些是注入上下文、哪些是用户输入。与 audit 一致。

### F7. Hardcoded Context Strings [LOW — 已验证]

`CAPABILITY_BRIEF`, `SUMMARY_PROTOCOL_*`, `THINKING_PROMPT_*` 均为 Python 字符串字面量。与 audit 一致。

### F8. Inbox Dedup Fragility [LOW — 已验证]

仅比较前 200 字符的 SHA256。与 audit 一致。

### F9. L3 Dual Discovery Path [LOW — 已验证]

SOP 通过 `skill_prompt_injector.py` 和 `insight_fixed_structure.txt` 两条路径发现。与 audit 一致。

### F10. Duplicate Ambiguous Follow-up Detection [NEW — 本轮发现]

两个模块各自实现了 ambiguous follow-up 检测：
- `core/agentmain.py:106` `_is_ambiguous_followup()` — 简单 prefix/exact match
- `core/context/recent_turns.py:66` `is_ambiguous_followup()` — lambda 模式集

两条路径的匹配集不完全一致，可导致 Classic 和 OpenAI 路径对同一输入做出不同 ambiguity 判断。

### F11. Duplicate Recent Context Building [NEW — 本轮发现]

两个模块各自实现了 recent context 构建：
- `core/agentmain.py:114` `_build_recent_context()` — `[RECENT CONVERSATION CONTEXT]` + clarification 指令
- `core/context/recent_turns.py:117` `build_recent_conversation_block()` — `[RECENT CONVERSATION]` + turn-structured

第一条仍在 Classic path 使用（`agentmain.py:487`），第二条在 OpenAI path 使用（`openai_agentmain.py:2479`）。格式不同，语义相似。

---

## 6. Keep / Wrap / Migrate / Deprecate / Delete Decisions

### 6.1 Context Sources

| Source | Decision | Reason | Migration Target |
|--------|----------|--------|-----------------|
| `assets/sys_prompt.txt` | **KEEP** | 稳定，单一职责 | — |
| `assets/insight_fixed_structure.txt` | **MIGRATE** | 当前耦合到 `build_legacy_memory_block()`，应归属 `ContextBuilder` | `core/context/context_builder.py` |
| `assets/global_mem_insight_template.txt` | **KEEP** | Bootstrap only | — |
| `assets/tools_schema.json` | **KEEP** | Tool 定义，非 context 关注 | — |
| `CAPABILITY_BRIEF` (hardcoded) | **MIGRATE** | 应从文件加载 | `assets/agent_capability_brief.txt` |
| `SUMMARY_PROTOCOL_*` (hardcoded) | **MIGRATE** | 同上 | `assets/summary_protocol.txt` |
| `THINKING_PROMPT_*` (hardcoded) | **KEEP** | 短字符串，极少变更 | — |

### 6.2 L1/L2 Read Paths

| # | Path | Decision | Replacement |
|---|------|----------|-------------|
| 1 | `legacy_global.py::read_legacy_l1_l2()` | **DEPRECATE** | `MemoryReader.read_global_memory()` |
| 2 | `legacy_global.py::build_legacy_memory_block()` | **DEPRECATE** | `ContextBuilder.build()` |
| 3 | `core/memory/reader.py::read_global_memory()` | **KEEP** (canonical) | 作为单向 path 保留 |
| 4 | `maintenance.py::build_scoped_memory_context()` | **MIGRATE** | keyword-filtering → `MemoryReader` |
| 5 | `core/context/memory_reader.py::MemoryReader` | **KEEP** (canonical) | 已是 canonical，与 #3 合并 |

**Target:** After migration: 1 read path — `core/context/memory_reader.py::MemoryReader`

### 6.3 Classic Injection Points

| Injection | Decision | Replacement |
|-----------|----------|-------------|
| `get_system_prompt()` L1/L2 部分 | **WRAP** | 保留缓存逻辑；调用 `ContextBuilder` 替代 `build_legacy_memory_block()` |
| `_build_recent_context()` | **MIGRATE** | → `ContextBuilder` 的 recent_turns block |
| `ga.py:727` 周期性 L1/L2 重注入 | **DEPRECATE** | Memory 应在 task start 通过 canonical path 注入 |
| `_get_anchor_prompt()` working memory | **MIGRATE** | → `ContextBuilder` working memory block |
| `do_start_long_term_update()` | **KEEP** | distillation trigger，独立关注点 |
| `agent_runner_loop()` | **KEEP** | 薄组装层，接收 pre-built context |

### 6.4 OpenAI Injection Points

| # | Injection | Decision | Replacement |
|---|-----------|----------|-------------|
| 1 | `_working_memory_message()` | **MIGRATE** | → `ContextBuilder` |
| 2 | `_build_context_runtime()` | **MIGRATE** | 已有 context_builder，接入 adapter |
| 3 | `build_recent_conversation_block()` | **MIGRATE** | 合并 Classic 路径版本 |
| 4 | `read_legacy_l1_l2()` injection | **DELETE** | 完全由 `ContextBuilder` 输出替代 |
| 5 | Route hint | **KEEP** | 简单字符串 |
| 6 | `build_answer_quality_context()` | **KEEP** | 内部改用 canonical reader |
| 7 | `build_optional_sop_context()` | **KEEP** | 同上 |
| 8 | `build_read_prefetch_context()` | **KEEP** | 单一关注点 |
| 9 | `build_clarification_request()` | **KEEP** | 单一关注点 |
| 10 | Skill activation policy | **KEEP** | 单一关注点 |
| 11 | Raw user query | **KEEP** | 这是用户输入，始终最后 |

**Target:** 11 个手写 `inputs.append()` 替换为 `OpenAIContextAdapter.inject(packet, inputs)`。

### 6.5 Write Paths

| Writer | Decision | Reason |
|--------|----------|--------|
| `agentmain.py` init (bootstrap L1/L2) | **KEEP** | Bootstrap only |
| `save_distilled_memory()` | **WRAP** | 加文件锁或委托给 `MemoryStore` |
| `write_distillation_candidate()` | **WRAP** | 同上 |
| `dedup_inbox()` | **KEEP** | 维护工具 |
| `archive_inbox_to_structured()` | **KEEP** | SQLite 事务，安全 |
| `do_start_long_term_update()` | **KEEP** | Agent-gated |
| `log_memory_access()` | **KEEP** | Audit log |
| `MemoryStore` 写入 | **KEEP** | 事务安全 |
| `_log_exchange()` | **KEEP** | 单线程 |
| `SessionStore` 写入 | **KEEP** | 事务安全 |

### 6.6 Structural Decisions

**Decision 1 — Context Injection Role:**
所有系统注入的 context block 必须用 `role: system`（API 支持时）或明确的 structural marker（如 `[PROJECT MEMORY]`、`[RECENT CONTEXT]`），不允许裸 `role: user` 注入。

**Decision 2 — Assistant-as-Fact:**
`<summary>` 和 assistant 输出不能作为 verified fact 用于记忆注入。Distillation 必须交叉引用工具执行结果。

**Decision 3 — Duplicate Module Consolidation:**
- `core/agentmain.py::_is_ambiguous_followup()` → **DEPRECATE**，统一用 `core/context/recent_turns.py::is_ambiguous_followup()`
- `core/agentmain.py::_build_recent_context()` → **DEPRECATE**，统一用 `core/context/recent_turns.py::build_recent_conversation_block()`

---

## 7. Proposed Canonical Memory / Context Pipeline

```
User Query
    │
    ▼
┌─ Conversation Pool / Recent Turns ─────────────────────────────┐
│  职责: 提供最近 N 轮对话的 structured summary                    │
│  输入: input_items (OpenAI format) 或 self.history (Classic)    │
│  输出: [RECENT CONTEXT] block (role: conversation)              │
│  不允许: 直接读文件、直接写 L1/L2                                │
│  迁移自: _build_recent_context() + build_recent_conversation_block() │
│  测试: T3, I1, I4                                               │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Tool Event Ledger ────────────────────────────────────────────┐
│  职责: 记录工具调用的事实结果（executed fact 的唯一证据）        │
│  输入: tool_calls + tool_results from agent_runner_loop         │
│  输出: ToolEvent 列表 (tool_name, args, result_summary, status) │
│  不允许: 保存 assistant text 作为事实；save 未执行的操作         │
│  迁移自: N/A (new)                                              │
│  测试: I5, T5                                                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Pending / Executed Change Classifier ─────────────────────────┐
│  职责: 区分 proposed change 和 executed change                  │
│  输入: agent 的 plan/thinking + ToolEvent Ledger                │
│  输出: proposed_changes: list, executed_changes: list           │
│  不允许: 将 pending proposal 写入长期记忆                        │
│  迁移自: N/A (new — 解决 F3)                                    │
│  测试: T5, I5                                                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Task Snapshot ────────────────────────────────────────────────┐
│  职责: 当前 task 的 compressed state（plan, progress, results） │
│  输入: Working memory + ToolEvent Ledger + Change Classifier    │
│  输出: TaskSnapshot (compact, <2000 chars)                      │
│  不允许: 包含完整 conversation history                           │
│  迁移自: _get_anchor_prompt() + _working_memory_message()       │
│  测试: I1, I3                                                   │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Memory Reader ────────────────────────────────────────────────┐
│  职责: 读取所有记忆来源（L1, L2, SQLite, session state）         │
│  输入: user_query, project_root, session_id                     │
│  输出: MemoryBundle (priority-ordered MemoryBlock list)         │
│  不允许: 写文件；修改 memory；直接嵌入 prompt                    │
│  迁移自: 5 条旧 L1/L2 读路径统一到此                            │
│  测试: T1, T2, I2                                               │
│  已实现: core/context/memory_reader.py::MemoryReader            │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Context Builder ──────────────────────────────────────────────┐
│  职责: 组装所有 source 为 ContextPacket；只调用 reader/ledger   │
│  输入: 来自上层各 stage 的输出                                   │
│  输出: ContextPacket (role-marked blocks, prioritized)          │
│  不允许: 直接读文件/SQLite；在自己内部拼接 injection string      │
│  迁移自: 11 个 openai_agentmain.py 手写 inputs.append()         │
│  测试: T3, T4, I1, I3, I4, I6                                  │
│  已实现: core/context/context_builder.py::ContextBuilder        │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Route-Specific Injection Gate ────────────────────────────────┐
│  职责: 按 route (chat/code/review/research/executor) 决定注入   │
│  输入: ContextPacket + route_target + policy_mode               │
│  输出: 适配后的 injection list (system prompt 或 inputs[])       │
│  不允许: 在 gate 内部新增 context source                         │
│  迁移自: openai_agentmain.py 中按 agent_name 的条件注入逻辑      │
│  测试: I1, E1, E2                                               │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Agent ────────────────────────────────────────────────────────┐
│  职责: 执行任务                                                  │
│  输入: 已组装的 messages/inputs + tools_schema                  │
│  输出: response + tool_calls                                    │
│  不允许: 自己构建 context；直接读 memory 文件                    │
└────────────────────────────────────────────────────────────────┘
```

### 硬性规则

1. Context Builder 只负责组装，不直接读文件/SQLite
2. Memory Reader 负责读取所有记忆来源
3. Injection Gate 按 route 决定注入内容
4. Tool Event Ledger 是 executed fact 的唯一证据
5. Assistant final 只是 text，不是 execution evidence
6. Pending proposal 必须和 executed change 分离
7. L1/L2 作为 legacy memory source，通过 reader 读取
8. OpenAI / Classic / handoff 最终都走同一个 context pipeline
9. 不允许继续在 openai_agentmain.py 内新增手写 context 拼接点
10. 不允许多个模块各自实现 ambiguous follow-up detector

---

## 8. Minimal Next Implementation Plan

### Phase M3: 建立统一只读层

| Item | Detail |
|------|--------|
| **修改文件** | `core/context/memory_reader.py` — 与 `core/memory/reader.py` 合并；`core/memory/legacy_global.py` — 添加 `@deprecated` comment |
| **不修改文件** | `core/agentmain.py`, `core/ga.py`, `core/openai_agentmain.py`, `core/agent_loop.py` |
| **新增文件** | `tests/architecture/test_context_boundaries.py` 补充 reader 边界测试 |
| **验收标准** | `MemoryReader.scoped_query()` 返回与 `read_legacy_l1_l2()` 字节一致的内容 |
| **测试** | T1, T2 (禁止其他模块直读 L1/L2) + I2 (parity 验证) |
| **回滚方式** | MemoryReader 是新增调用路径；旧路径未删除，行为不变 |
| **风险** | 低。只读，不改变现有 runtime 行为 |

### Phase M4: 建立 ContextBuilder Preview

| Item | Detail |
|------|--------|
| **修改文件** | `core/context/context_builder.py` — 增加 recent_turns + working_memory 作为 source |
| **不修改文件** | 所有 runtime 文件 |
| **新增文件** | `tests/integration/test_context_builder_output.py` |
| **验收标准** | `ContextBuilder.build()` 返回包含 all sources 的 `ContextPacket`，total_chars ≤ max_chars |
| **测试** | I1, I3 (output validity + size budget) |
| **回滚方式** | ContextBuilder 是纯构建器，不接入 runtime |
| **风险** | 低。Preview mode 只写 JSON 到 `temp/context_audit/`，不注入 |

### Phase M5: OpenAI Path 迁移到 ContextBuilder

| Item | Detail |
|------|--------|
| **修改文件** | `core/openai_agentmain.py` — `inputs` 列表由 `OpenAIContextAdapter` 构建 |
| **不修改文件** | `core/agent_loop.py`, `core/ga.py`, `core/agentmain.py` |
| **新增文件** | `core/context/adapters.py` (OpenAIContextAdapter + ClassicContextAdapter) |
| **验收标准** | OpenAI path 产生与迁移前字节一致的 context（parity 验证通过） |
| **测试** | I4 (dual path parity) + E2 (OpenAI path migration) |
| **回滚方式** | `GA_CONTEXT_RUNTIME_MODE=preview` → 双轨并行；`=inject` → 新路径；unset → 旧路径 |
| **风险** | **Medium**。OpenAI path 的 11 个 inputs.append() 是核心逻辑；需 parity 验证后切换 |

### Phase M6: Classic Handoff 短桥接

| Item | Detail |
|------|--------|
| **修改文件** | `core/agentmain.py` — `_build_recent_context()` 改为调用 `build_recent_conversation_block()` |
| **不修改文件** | `core/agent_loop.py`, `core/ga.py`, `get_system_prompt()` |
| **新增文件** | 无 |
| **验收标准** | Classic path handoff brief 使用 unified recent_turns 格式 |
| **测试** | E1 (Classic path migration) |
| **回滚方式** | `GENERIC_AGENT_RECENT_TURNS=0` 关闭 |
| **风险** | **Low**。仅改 handoff brief 格式，不改变 agent_loop |

### Phase M7: ToolEvent / PendingChange 最小账本

| Item | Detail |
|------|--------|
| **修改文件** | `core/agent_loop.py` — 添加 ToolEvent recording hook |
| **不修改文件** | `core/ga.py`, `core/openai_agentmain.py`, L1/L2 文件 |
| **新增文件** | `core/context/tool_event_ledger.py`, `core/context/change_classifier.py` |
| **验收标准** | 区分 proposed vs executed changes；ToolEvent 记录在账本中 |
| **测试** | T5 (no assistant-as-fact) + I5 (tool event recording) |
| **回滚方式** | Env gate `GA_TOOL_EVENT_LEDGER=0` |
| **风险** | **Medium**。新数据结构；需确保不阻塞 agent loop |

### Phase M8: 长期写入 Preview

| Item | Detail |
|------|--------|
| **修改文件** | `core/memory/distillation.py` — 增加 cross-reference 验证 |
| **不修改文件** | `history_memory_inbox.md`, `catalog.sqlite` schema |
| **新增文件** | `tests/integration/test_distillation_verified.py` |
| **验收标准** | Distillation preview 输出包含 tool_cross_reference 字段 |
| **测试** | I5 (distillation verification) |
| **回滚方式** | Preview mode — 不写 inbox |
| **风险** | **Low**。Preview only，不改变写入行为 |

---

## 9. Risks

| # | Risk | Mitigation |
|---|------|------------|
| R1 | 5 条 L1/L2 读路径在被 deprecate 前继续 diverging | 每个 deprecation 添加 `@deprecated` warning（一次 per session） |
| R2 | ContextBuilder 与当前 11 条 OpenAI path 的行为不等价 | Phase M5 parity 验证；`GA_CONTEXT_RUNTIME_MODE=preview` 双轨并行 |
| R3 | Classic path 的 `get_system_prompt()` 缓存 60s 机制与 ContextBuilder 冲突 | M3 不改 `get_system_prompt()`；只在内部 reader 合并 |
| R4 | Tool Event Ledger 是全新抽象，无现有参考 | M7 先做最小实现（只记录 tool_name + result_summary）；不改变现有 tool dispatch |
| R5 | OpenAIContextAdapter 必须在 `openai_agentmain.py` 内替换 11 个 inputs.append() | M5 用 env gate 控制新旧路径切换；旧路径保留 |

---

## 10. Files Not Modified (This Phase)

```
core/agentmain.py          — 不改
core/agent_loop.py          — 不改
core/ga.py                  — 不改
core/openai_agentmain.py    — 不改（除 M5 迁移时）
core/llmcore.py             — 不改
core/memory/legacy_global.py — 不改（添加 deprecated comment 除外）
core/memory/maintenance.py  — 不改
core/memory/store.py        — 不改
core/memory/distillation.py — 不改
core/memory/write_gate.py   — 不改
memory/global_mem_insight.txt — 不改
memory/global_mem.txt       — 不改
memory/history_memory_inbox.md — 不改
memory/catalog.sqlite       — 不改
frontends/stapp.py           — 不改
frontends/chatapp_common.py  — 不改
assets/sys_prompt.txt       — 不改
```

---

*Report: 2026-05-05. Code-verified against the current working tree on branch `chore/phase1-security`.*
*Next step: Phase M3 — 建立统一只读层。*
