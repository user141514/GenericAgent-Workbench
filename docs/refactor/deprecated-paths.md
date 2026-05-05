# Deprecated Paths

> Inventory of paths marked for deprecation or deletion.
> This is a snapshot. Update when migration phases complete.

## Active Deprecations (Phase 2 — Migration)

| # | Path | File:Line | Status | Replacement | Removal Target |
|---|------|-----------|--------|-------------|----------------|
| D1 | `read_legacy_l1_l2()` | `core/memory/legacy_global.py:48` | **Active** | `core/context/memory_reader.py::MemoryReader` | Phase 4 |
| D2 | `build_legacy_memory_block()` | `core/memory/legacy_global.py:93` | **Active** | `core/context/context_builder.py::ContextBuilder` | Phase 4 |
| D3 | Classic path `get_global_memory()` call in `get_system_prompt()` | `core/agentmain.py:79` | **Active** | `ClassicContextAdapter.inject()` | Phase 3 |
| D4 | Classic path periodic L1/L2 re-injection | `core/ga.py:727` | **Active** | Removed (canonical path handles at task start) | Phase 3 |
| D5 | OpenAI path `read_legacy_l1_l2()` injection | `core/openai_agentmain.py:2493` | **Active** | `OpenAIContextAdapter.inject()` | Phase 3 |
| D6 | OpenAI path `_working_memory_message()` | `core/openai_agentmain.py:2457` | **Active** | `ContextBuilder` working memory block | Phase 3 |
| D7 | OpenAI path 10-item manual `inputs` assembly | `core/openai_agentmain.py:2456-2784` | **Active** | `OpenAIContextAdapter` | Phase 3 |

## Future Deprecations (Phase 3 — Parity Confirmed)

| # | Path | File:Line | Condition |
|---|------|-----------|-----------|
| F1 | Classic path `_build_recent_context()` | `core/agentmain.py:114` | After `ContextBuilder` recent turns block is parity-verified |
| F2 | Classic path `_get_anchor_prompt()` | `core/ga.py:657` | After working memory is in `ContextBuilder` |
| F3 | `build_scoped_memory_context()` | `core/memory/maintenance.py:119` | After keyword filtering is in `MemoryReader` |
| F4 | `core/context/memory_reader.py` (experimental) | `core/context/memory_reader.py` | Merge into canonical `MemoryReader` |

## Candidates for Deletion (Phase 4 — Old Paths Removed)

| # | Path | Condition |
|---|------|-----------|
| X1 | Entire `core/memory/legacy_global.py` module | After all callers migrated |
| X2 | `core/memory/reader.py` duplicate read methods | After merged into canonical reader |
| X3 | `core/context/memory_reader.py` (after merge) | After merge into `core/context/reader.py` |

## Hardcoded Context (Migrate, Not Delete)

| # | Item | File:Line | Migration Target |
|---|------|-----------|------------------|
| H1 | `CAPABILITY_BRIEF` string | `core/openai_agentmain.py:71` | `assets/agent_capability_brief.txt` |
| H2 | `SUMMARY_PROTOCOL_ZH` string | `core/openai_agentmain.py:80` | `assets/summary_protocol_zh.txt` |
| H3 | `SUMMARY_PROTOCOL_EN` string | `core/openai_agentmain.py:89` | `assets/summary_protocol_en.txt` |

## Race Condition Fixes (Repair, Not Delete)

| # | Location | Fix |
|---|----------|-----|
| R1 | `chatapp_common.py:592` `save_distilled_memory()` | Add `fcntl.flock()` / `msvcrt.locking()` or delegate to `MemoryStore` |
| R2 | `distillation.py:235` `write_distillation_candidate()` | Same as R1 |

## Rules for Deprecated Code

1. Deprecated functions must have a `@deprecated` decorator or `# DEPRECATED: phase=N, replaced_by=X` comment.
2. Deprecated code must log a warning (once per session) when called: `logger.warning("DEPRECATED: X called. Use Y instead.")`
3. No new callers may be added to deprecated paths.
4. Deprecated code is removed in the phase after its replacement is parity-verified.

---

*Inventory: 2026-05-05. Update after each migration phase.*
