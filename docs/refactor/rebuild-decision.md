# Rebuild Decision: Keep / Wrap / Migrate / Deprecate / Delete

> Phase 1 classification only. No runtime changes authorized at this stage.
> Each decision records the current state and the recommended future state.

---

## Decision Framework

| Label | Meaning |
|---|---|
| **KEEP** | No change needed. Maintain as-is. |
| **WRAP** | Keep internal logic, add a canonical interface wrapper. |
| **MIGRATE** | Move to new canonical path. Old path deprecated. |
| **DEPRECATE** | Mark for removal. No new callers. Existing callers continue until migration complete. |
| **DELETE** | Remove entirely. No callers remain. |

---

## Context Sources

| Source | Decision | Rationale | Migration Target |
|---|---|---|---|
| `assets/sys_prompt.txt` | KEEP | Stable, simple, single responsibility | — |
| `assets/insight_fixed_structure.txt` | MIGRATE | Currently coupled to `build_legacy_memory_block()`. Should be owned by canonical context builder | `core/context/context_builder.py` |
| `assets/global_mem_insight_template.txt` | KEEP | Bootstrap-only. Rarely changes. | — |
| `assets/tools_schema.json` | KEEP | Tool definitions. Separate concern from context. | — |
| `CAPABILITY_BRIEF` (hardcoded) | MIGRATE | Hardcoded in Python. Should be a template file. | `assets/agent_capability_brief.txt` |
| `SUMMARY_PROTOCOL_*` (hardcoded) | MIGRATE | Hardcoded in Python. Should be a template file. | `assets/summary_protocol.txt` |

---

## Memory Read Paths

| Path | File | Decision | Rationale |
|---|---|---|---|
| 1 | `core/memory/legacy_global.py::read_legacy_l1_l2()` | **DEPRECATE** | Raw text read. Replaced by canonical `MemoryReader` |
| 2 | `core/memory/legacy_global.py::build_legacy_memory_block()` | **DEPRECATE** | Template-wrapped read. Replaced by `ContextBuilder` |
| 3 | `core/memory/reader.py::read_global_memory()` | **KEEP** (as canonical) | Current most-structured reader. Becomes the single path. |
| 4 | `core/memory/maintenance.py::build_scoped_memory_context()` | **MIGRATE** | Keyword-filtering logic should merge into canonical reader |
| 5 | `core/context/memory_reader.py::read_global_memory()` | **MIGRATE** | Experimental but architecturally correct. Merge with path 3. |

**Target:** After migration, exactly **1** read path for L1/L2, exposed via `core/context/context_builder.py` as the single entry point.

---

## Injection Points

### Classic Path

| Injection | Decision | Rationale |
|---|---|---|
| `agentmain.py::get_system_prompt()` | **WRAP** | Keep cache logic. Wrap to call `ContextBuilder` instead of `build_legacy_memory_block()` |
| `agentmain.py::_build_recent_context()` | **MIGRATE** | Move to `ContextBuilder` as `build_recent_conversation_block()` |
| `ga.py::turn_end_callback()` L1/L2 re-injection | **DEPRECATE** | Removes periodic L1/L2 re-injection. Memory should come from canonical path at task start. |
| `ga.py::_get_anchor_prompt()` | **MIGRATE** | Working memory block should be built by `ContextBuilder` |
| `ga.py::do_start_long_term_update()` | KEEP | Distillation trigger. Separate from context injection. |
| `agent_loop.py::agent_runner_loop()` | KEEP | Thin assembly layer. Should receive pre-built context. |

### OpenAI Path

| Injection | Decision | Rationale |
|---|---|---|
| `_working_memory_message()` | **MIGRATE** | Move to `ContextBuilder` |
| `_build_context_runtime()` | **MIGRATE** | Already architecturally correct. Feed into `ContextBuilder` |
| `build_recent_conversation_block()` | **MIGRATE** | Already in `core/context/`. Consolidate with Classic path version. |
| `read_legacy_l1_l2()` injection | **DELETE** | Replace completely with canonical `ContextBuilder` output. |
| Route hint injection | KEEP | Simple string. No architectural change needed. |
| `build_answer_quality_context()` | KEEP | Single concern. Use canonical reader internally. |
| `build_optional_sop_context()` | KEEP | Single concern. Use canonical reader internally. |
| `build_read_prefetch_context()` | KEEP | Single concern. |
| `build_clarification_request()` | KEEP | Single concern. |
| Raw user query | KEEP | This IS the user input. Always last. |

**Target:** OpenAI path `inputs` list should be:
1. System-level blocks (built by `ContextBuilder`) as `role: system` or clearly labeled
2. Context blocks from canonical sources — NOT hand-rolled
3. User query as the final entry

---

## Write Paths

| Writer | Decision | Rationale |
|---|---|---|
| `agentmain.py` init (create default L1/L2) | KEEP | Bootstrap only. Harmless. |
| `save_distilled_memory()` (frontend inbox write) | **WRAP** | Add file locking or delegate to `MemoryStore` |
| `write_distillation_candidate()` (backend inbox write) | **WRAP** | Same — add locking or delegate |
| `dedup_inbox()` | KEEP | Maintenance utility. OK as-is. |
| `archive_inbox_to_structured()` | KEEP | Already uses SQLite transactions. Safe. |
| `do_start_long_term_update()` (agent tool-call write) | KEEP | Agent-gated. Requires explicit tool call. |
| `log_memory_access()` | KEEP | Audit log. Low risk. |
| `MemoryStore` SQLite writes | KEEP | Transactional. Correct. |

---

## Structural Decisions

### Context Injection Role

**Decision:** All system-injected context blocks should use a dedicated role or clear structural marker, not bare `{"role": "user"}` entries indistinguishable from actual user input.

**Recommended markers:**
- System blocks → `role: system` (where API supports it) or `[SYSTEM CONTEXT]` header
- Memory blocks → `[PROJECT MEMORY]` header (already partially used)
- Recent conversation → `[RECENT CONTEXT]` header (already partially used)

### Assistant-as-Fact

**Decision:** `<summary>` tags and assistant output must NOT be treated as verified facts for memory injection. Distillation must cross-reference tool execution results where available.

### Repair vs Rebuild Gate

| Scope | Verdict | Rationale |
|---|---|---|
| Context assembly | **Rebuild** | 5 duplicate L1/L2 paths; 10+ injection points in OpenAI path. Wrapping individual paths creates more complexity than a single canonical pipeline. |
| Write paths | **Repair** | Only 2 race conditions to fix (add locking). Everything else works. |
| Memory storage format | **Repair** | L1/L2 as markdown is adequate. Structured memory (SQLite) already exists as upgrade path. |
| SOP / Skill injection | **Repair** | Single entry point. Works. Add discovery consistency. |

---

*Decision record: 2026-05-05. Review before any migration begins.*
