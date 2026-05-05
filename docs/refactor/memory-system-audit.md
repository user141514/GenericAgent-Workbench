# Memory System Audit

> Phase 1 of the staged refactor review mechanism.
> This document inventories what exists. It does not prescribe changes.

## 1. Context Sources Inventory

### 1.1 Static Templates

| Source | Loaded by | Location |
|---|---|---|
| `assets/sys_prompt.txt` (or `_en.txt`) | `core/agentmain.py:76` `get_system_prompt()` | System prompt base |
| `assets/insight_fixed_structure.txt` | `core/memory/legacy_global.py:99` `build_legacy_memory_block()` | L1→L2 structural wrapper |
| `assets/global_mem_insight_template.txt` | `core/agentmain.py:55-56` | Default L1 when file absent |
| `assets/tools_schema.json` (or `_cn.json`) | `core/agentmain.py:41` (module level) | Tool definitions |
| `CAPABILITY_BRIEF` string literal | `core/openai_agentmain.py:71` (hardcoded in Python) | Agent instructions |
| `SUMMARY_PROTOCOL_ZH` / `_EN` string literals | `core/openai_agentmain.py:80-89` (hardcoded in Python) | Summary protocol |

### 1.2 Memory Files (L1 / L2 / Inbox)

**L1 — `memory/global_mem_insight.txt`**

Read by 5 independent code paths:

| # | File | Function | Line | Format |
|---|------|----------|------|--------|
| 1 | `core/memory/legacy_global.py` | `read_legacy_l1_l2()` | 48 | Raw text |
| 2 | `core/memory/legacy_global.py` | `build_legacy_memory_block()` | 93 | Wrapped in `insight_fixed_structure.txt` template |
| 3 | `core/memory/reader.py` | `read_global_memory()` | 24 | `MemoryBlock` with priority |
| 4 | `core/memory/maintenance.py` | `build_scoped_memory_context()` | 144 | Keyword-filtered paragraphs |
| 5 | `core/context/memory_reader.py` | `read_global_memory()` | 89 | `MemoryBlock` with priority |

**L2 — `memory/global_mem.txt`**

Read by the same 5 code paths as L1 (lines 59, 115, 34, 144, 90 respectively).

**Inbox — `memory/history_memory_inbox.md`**

Read by:
- `frontends/chatapp_common.py::save_distilled_memory()` (line 601) — dedup check
- `core/memory/maintenance.py::dedup_inbox()` (line 30) — deduplication
- `core/memory/maintenance.py::score_inbox_entries()` — scoring
- `core/memory/maintenance.py::archive_inbox_to_structured()` (line 222) — archiving

### 1.3 Skills / SOP Files (L3)

All files in `memory/*.md` and `memory/*.py`. Read via:
- `core/skills/skill_prompt_injector.py::SkillSelector.select_skill_matches_for_task()`
- Referenced by `insight_fixed_structure.txt` (second discovery path)

Key files: `autonomous_operation_sop.md`, `memory_management_sop.md`, `verify_sop.md`, `plan_sop.md`, `coding_karpathy_sop.md`, `skill_best_practices.md`, `streamlit_pitfalls.md`, `subagent.md`, ~17 total.

### 1.4 Structured Memory (SQLite FTS5)

- `memory/catalog.sqlite` — optional. Read by `core/memory/store.py::MemoryStore.search_evidence_chunks()` (line 364).
- Accessed via `core/memory/reader.py::search_structured_memory()` (line 69) and `core/context/memory_reader.py::read_structured_memory()` (line 128).

### 1.5 Raw Session History

- `memory/L4_raw_sessions/` — referenced by `insight_fixed_structure.txt`.

### 1.6 History / Log Files

- `temp/model_responses/model_responses_*.txt` (Classic path)
- `temp/model_responses_openai/model_responses_*.txt` (OpenAI path)
- Both read by `frontends/chatapp_common.py::format_restore()` (line 286).

### 1.7 Context Runtime (Experimental)

- `core/context/` — `workspace_probe`, `project_identity`, `runtime_identity`, `memory_reader`, `context_builder`.
- Gated by `GA_CONTEXT_RUNTIME_ENABLED` env var.
- Reads L1/L2, structured memory, session state, workspace info.

---

## 2. Injection Points Inventory

### 2.1 Classic Path (`core/agentmain.py` + `core/agent_loop.py` + `core/ga.py`)

| Injection | Where | When | Content |
|---|---|---|---|
| System prompt | `agentmain.py:71` `get_system_prompt()` | Task init, cached 60s | `sys_prompt.txt` + date + L1/L2 via `build_legacy_memory_block()` |
| Extra system prompt | `agentmain.py:469` | Task init | `extra_sys_prompt` from backend |
| Recent conversation context | `agentmain.py:114` `_build_recent_context()` | Each user query | `[RECENT CONVERSATION CONTEXT]` from `self.history` |
| Working memory | `ga.py:657` `_get_anchor_prompt()` | Feishu source only | History + key_info block |
| Periodic L1/L2 re-injection | `ga.py:727` `turn_end_callback()` | Every 10 turns | `get_global_memory()` via next_prompt |
| Memory management SOP | `ga.py:641` `do_start_long_term_update()` | Distillation trigger | `get_global_memory()` + management SOP |

Final assembly in `agent_runner_loop()` (`core/agent_loop.py:358`):
- `messages[0]` = `{"role": "system", "content": system_prompt}`
- `messages[1]` = user input (with recent context prepended)

### 2.2 OpenAI / Orchestration Path (`core/openai_agentmain.py`)

Assembled in `_run_task_async()` (line ~2345). All injected as separate `{"role": "user", "content": "..."}` entries in `inputs`:

| # | Block | Line | Gating |
|---|-------|------|--------|
| 1 | Working memory (last 20 history entries) | 2457 | Always |
| 2 | Context runtime packet | 2463 | `GA_CONTEXT_RUNTIME_ENABLED` |
| 3 | Recent conversation block (last 5 turns, 6000 chars) | 2478 | Always |
| 4 | Legacy L1/L2 memory (`[LEGACY PROJECT MEMORY]`) | 2493 | `GA_OPENAI_LEGACY_MEMORY` (default enabled) |
| 5 | Route hint (`[ROUTER_HINT]`) | 2712 | When set |
| 6 | Answer quality context | 2714 | Code/review/research agents |
| 7 | SOP / Skill context | 2717 | Planner agent |
| 8 | Read prefetch (background file read) | 2731 | When configured |
| 9 | Ambiguous follow-up clarification | 2783 | Ambiguous query, no recent turns |
| 10 | Raw user query | 2784 | Always |

All fed to `Runner.run_streamed(selected_agent, input=inputs)` at line 2841.
Individual agents have own `instructions=` (line 1849) with `CAPABILITY_BRIEF` + `_summary_protocol()`.

### 2.3 LLM Core Wrappers (`core/llmcore.py`)

| Wrapper | Line | How system prompt is injected |
|---|---|---|
| `ClaudeSession.raw_ask()` | 729 | `payload["system"] = self.system` |
| `NativeClaudeSession.raw_ask()` | 823 | `payload["system"]` or prepended to first message |
| `LLMSession.make_messages()` | 774 | `{"role": "system", "content": ...}` |
| `NativeOAISession.raw_ask()` | 911 | `{"role": "system", "content": ...}` |

---

## 3. Write Paths Inventory

### 3.1 Memory File Writes

| Writer | File/Line | Target | Locking |
|---|---|---|---|
| `agentmain.py:50-56` | Module init | `global_mem.txt`, `global_mem_insight.txt` (create if absent) | None |
| `chatapp_common.py:592` `save_distilled_memory()` | Frontend | `history_memory_inbox.md` (append) | None — **race condition** |
| `distillation.py:235` `write_distillation_candidate()` | Core memory | `history_memory_inbox.md` (append) or `temp/distillation_previews/` | None — **race condition** |
| `maintenance.py:30` `dedup_inbox()` | Core memory | `history_memory_inbox.md` (rewrite) | None |
| `maintenance.py:222` `archive_inbox_to_structured()` | Core memory | `catalog.sqlite` + truncate inbox | SQLite transaction (safe) |
| `ga.py:641` `do_start_long_term_update()` | Classic handler | L1/L2 via agent tool calls | Agent-gated |
| `ga.py:162` `log_memory_access()` | Classic handler | `memory/file_access_stats.json` | None |

### 3.2 Model Response Logging

- `temp/model_responses/model_responses_*.txt` (Classic path)
- `temp/model_responses_openai/model_responses_*.txt` (OpenAI path, written via `chatapp_common.py::_log_exchange()`)

### 3.3 Structured Memory (SQLite)

- `core/memory/store.py`: `add_memory_item()` (86), `add_memory_candidate()` (158), `add_evidence_chunk()` (222), `add_memory_event()` (313)
- All gated by `MemoryWriteGate` (source types: `distiller`, `promoter`, `manual_user`, `system_migration`)
- Write-safe via SQLite transactions

---

## 4. Failure Pattern Diagnosis

### F1. Duplicate L1/L2 Read Paths (Severity: CRITICAL)

Five independent code paths read the same two files with three different formatting strategies. A change to L1/L2 structure must be replicated in all five places, or the model sees stale/inconsistent memory across paths.

**Impact:** Memory inconsistency between Classic and OpenAI paths. Hard to audit what the model actually received.

### F2. System Prompt Caching Staleness (Severity: MEDIUM)

`agentmain.py:74` — system prompt cached for 60 seconds with no write-triggered invalidation. If a tool modifies L1/L2 during a task and the next query starts within 60 seconds, the model receives stale memory.

**Impact:** Temporal inconsistency in memory read by the model.

### F3. Assistant Output as Executed Fact (Severity: HIGH)

| Location | Mechanism |
|---|---|
| `ga.py:669` `_safe_summary()` | `<summary>` tag extracted and stored as `history_info` |
| `openai_agentmain.py:2969` `_extract_summary_line()` | Summary extracted from final output |
| `chatapp_common.py:494` `distill_conversation()` | Key replies extracted without verification |

No verification against actual tool execution results. A hallucinated summary propagates into future turns' working memory and distillation candidates.

**Impact:** Error propagation chain. Hallucinated facts become "memory."

### F4. Unbounded Context Growth (Severity: MEDIUM)

| Location | Issue |
|---|---|
| `openai_agentmain.py:238` `_working_memory_message()` | 20 history entries, no per-entry char budget |
| `ga.py:659` `_get_anchor_prompt()` | 20 history_info entries, no char budget |
| `context/recent_turns.py:117` | 6000 char total budget but no per-turn cap |
| `chatapp_common.py:592` `save_distilled_memory()` | Inbox is append-only with no size cap |

**Impact:** Context window pressure. Single large tool output can dominate recent context.

### F5. Race Conditions in Inbox Writes (Severity: MEDIUM)

`save_distilled_memory()` and `write_distillation_candidate()` both do read-check-write without file locking. Concurrent agents can overwrite each other's entries.

**Impact:** Silent data loss in inbox. Only structured memory (SQLite) writes are safe.

### F6. Context Injection Confusion in OpenAI Path (Severity: HIGH)

Up to 10 separate `{"role": "user"}` entries are appended to `inputs` before the actual user query. The model has no structural way to distinguish injected context from genuine user input. All blocks use the same `role: user` format.

**Impact:** The routing agent or planner may misattribute injected context as user instruction.

### F7. Hardcoded vs. Template Context (Severity: LOW)

`CAPABILITY_BRIEF` and `SUMMARY_PROTOCOL_*` are Python string literals in `openai_agentmain.py`, not loaded from template files. Changes require code edits.

**Impact:** Maintenance friction. Inconsistent with `sys_prompt.txt` template approach.

### F8. Inbox Dedup Fragility (Severity: LOW)

`dedup_inbox()` compares only first 200 characters (SHA256). Semantically different entries with identical openings collide.

**Impact:** Rare but possible data loss during maintenance deduplication.

### F9. L3 Dual Discovery Path (Severity: LOW)

SOPs are discovered via `skill_prompt_injector.py` (from skill manifests) AND via `insight_fixed_structure.txt` references to `memory/*.md`. Two sources of truth for what constitutes a valid SOP.

**Impact:** Ambiguity in SOP inventory.

---

## 5. Summary Statistics

| Metric | Count |
|---|---|
| Context source types | 7 (templates, memory files, SOPs, SQLite, sessions, logs, runtime) |
| L1/L2 read paths | 5 |
| Classic injection points | 5 |
| OpenAI injection points | 10 |
| Write paths | 11 |
| Failure patterns | 9 |
| Race conditions | 2 (inbox writes) |
| Duplicate read paths | 5 (L1/L2) |

---

*Audit prepared: 2026-05-05. This is a snapshot. The actual code may diverge.*
