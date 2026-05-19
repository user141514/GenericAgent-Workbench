# ADR: Frontend-Agent Decoupling — Architecture Checkpoint

Date: 2026-05-18
Status: accepted — updated 2026-05-18 (Phase OA1: OpenAIOrchestratedAgent native AgentBackend)
Supersedes: implicit queue.Queue[dict] protocol (pre-Phase 0)

## Context

GAgent-Multi had 10 frontends each directly calling `agent.put_task()` and consuming a raw `queue.Queue[dict]`. Frontends duplicated drain logic, agent output had no type, and the `core/runtime/` event infrastructure was built but unwired. A multi-phase decoupling was executed to define protocols, migrate frontends, and extract services.

This ADR captures the checkpoint state: what is stable, what is deferred, and what the next phase should NOT do.

## Decision

### 1. Stable Boundaries (completed)

| Boundary | Rule | Verified |
|----------|------|----------|
| `core/protocol/` | Zero dependencies on `core.runtime`, `core.agentmain`, `frontends/`, any third-party library. stdlib only. | ✅ grep confirms 0 matches |
| `frontends/services/` | Zero `import streamlit`. Zero `st.session_state` access. Zero UI output (`st.success` etc.). | ✅ 0 imports, only docstrings mention them |
| `AgentBackend` ABC | `submit(AgentInput) -> AgentOutputChannel` is the canonical task entry | ✅ 3 frontends + 1 Qt app use it |
| `ensure_agent_backend()` | All `dispatch_agent` paths go through this. Native AgentBackend passes through; legacy `put_task`-only objects get wrapped. | ✅ 3 call sites |
| `put_task()` | Retained, delegates to `submit()`. Not removed. | ✅ 2 definitions preserved |
| `__main__` blocks | Retained with deprecated comments. `launch.pyw` still depends on them. | ✅ Not removed |

### 2. Current Layer Diagram

```
┌─────────────────────────────────────────────┐
│  frontends/ (UI + session_state)             │
│  stapp.py  stapp_mobile.py  stapp2.py        │
│  qtapp.py                                    │
│                                              │
│  calls: ensure_agent_backend(dispatch_agent) │
│         → backend.submit(AgentInput)          │
│         → AgentOutputDrainer(channel)         │
│         → drainer.collect()                   │
└──────────────┬──────────────────────────────┘
               │ depends on
┌──────────────▼──────────────────────────────┐
│  frontends/services/ (no streamlit)          │
│  FileUploadService                           │
│  HistoryRestoreService                       │
│  reset_agent_conversation_state()             │
│                                              │
│  depends on: chatapp_common, file_processor  │
└──────────────┬──────────────────────────────┘
               │ depends on
┌──────────────▼──────────────────────────────┐
│  core/protocol/ (stdlib only)                │
│  AgentInput  AgentOutputEvent                │
│  AgentOutputChannel  QueueOutputChannel      │
│  AgentBackend (ABC)                         │
│  AgentOutputDrainer  AgentOutputFormatter    │
└──────────────┬──────────────────────────────┘
               │ depends on
┌──────────────▼──────────────────────────────┐
│  core/agentmain.py (GeneraticAgent)          │
│  core/openai_agentmain.py (Orchestrator)     │
│  core/agent_loop.py                          │
│  core/runtime/ (host, events, state machine) │
│  core/agent_factory.py                       │
└─────────────────────────────────────────────┘
```

### 3. Protocol Layer Constraints

**ALLOWED imports in `core/protocol/`**:
- `from .module` (intra-package)
- stdlib: `abc`, `dataclasses`, `queue`, `threading`, `typing`, `json`, `os`, `re`

**FORBIDDEN imports in `core/protocol/`**:
- `core.runtime` (any submodule)
- `core.agentmain` / `core.openai_agentmain`
- `frontends/` (any file)
- Any third-party library

### 4. frontends/services Constraints

**ALLOWED**:
- Python stdlib
- `frontends.chatapp_common` (pure functions)
- `frontends.file_processor` (pure functions)
- dataclass / plain data types

**FORBIDDEN**:
- `import streamlit`
- `st.session_state` read/write
- `st.success()` / `st.error()` / `st.toast()` / any UI output
- `core.agentmain` / concrete agent classes
- `core.runtime`
- `frontends.stapp` / `stapp_mobile` / `qtapp` / `stapp2` (reverse dependency)

### 5. AgentBackend Contract Status

| Implementation | How | Status |
|---------------|-----|--------|
| `GeneraticAgent(AgentBackend)` | Native. Has `submit()`, `is_running` property, all 6 ABC methods. | ✅ Complete (Phase 5) |
| `OpenAIOrchestratedAgent(AgentBackend)` | Native. Has `submit()`, `is_running` property, all 6 ABC methods. | ✅ Complete (Phase OA1) |
| `_LegacyAgentAdapter(AgentBackend)` | Adapter. Wraps `put_task()` + `abort()` + `is_running` into `submit()`. | ✅ Retained as fallback |

**Frontend dispatch is now fully unified:**

```
frontends → ensure_agent_backend(agent) → AgentBackend.submit(AgentInput)
          → AgentOutputChannel → AgentOutputDrainer
```

Both `GeneraticAgent` and `OpenAIOrchestratedAgent` are native `AgentBackend` implementations. `ensure_agent_backend()` does `isinstance(obj, AgentBackend)` which returns `True` for both — no adapter overhead. The `_LegacyAgentAdapter` is retained only for potential future legacy agents that expose `put_task()` but not `submit()`.

### 6. Phase OA1 Milestone

**Before**:
```
classic  → submit()  ← native
openai   → adapter   ← wraps put_task()
```

**After**:
```
classic  → submit()  ← native
openai   → submit()  ← native
adapter  → fallback  ← for other legacy agents only
```

`submit()` delegates to `put_task()` internally; no recursion. `put_task()` is retained as a legacy API, unchanged. `load_agent("openai")` is unblocked and returns a native `AgentBackend`.

### 7. Why AgentSessionService Was Not Extracted

Phase A0-audit examined `start_agent_task()`, `poll_agent_output()`, stop handling, and cleanup across all 4 migrated frontends. Key findings:

- `start_agent_task()` signatures differ: stapp takes `dispatch_agent`, stapp_mobile adds `task_id`, stapp2 uses fixed `agent`.
- `poll_agent_output()` syncs different filters: stapp syncs `stop_requested`, stapp_mobile syncs `stop_requested + task_id`, stapp2 syncs `stopping` (different name).
- Cleanup differs: stapp does inline reset, stapp_mobile calls `reset_agent_state()`, stapp2 calls `finish_streaming_message()`, qtapp does inline.
- Forced timeout exists in 3 of 4, with different implementations.

**Decision: DO NOT extract now.** The differences are meaningful (not accidental duplication), and the `AgentOutputDrainer` shared abstraction is already sufficient. Forcing unification would add complexity without value.

### 8. Why DistillationService Was Not Extracted

Phase D0-audit found that `distill_conversation()`, `save_distilled_memory()`, and `delete_history_file()` already live in `chatapp_common.py` as pure functions with zero Streamlit dependency. The stapp.py code around them is entirely Streamlit UI (`st.button`, `st.expander`, `st.success`, `st.session_state`) and agent state mutation (`agent.abort()`, `agent.history`, `backend.history`).

**Decision: DO NOT extract a service wrapper.** The business logic is already separated. Adding a service class would be a thin passthrough that adds no value and introduces an extra import layer.

### 9. Current Technical Debt

| Item | Severity | Status |
|------|----------|--------|
| `OpenAIOrchestratedAgent` native AgentBackend | — | ✅ Resolved (Phase OA1) |
| IM bots (wechat/tg/qq/dingtalk/wecom/feishu) not migrated | LOW | User decided not to continue; still use raw `put_task()` |
| `put_task()` retained for backward compat | LOW | Delegates to `submit()`; can be removed when all callers migrated |
| `__main__` blocks retained for `launch.pyw` | LOW | Deprecated comments added |
| No Streamlit end-to-end tests | MEDIUM | Frontend migration verified by static tests only |
| `_LegacyAgentAdapter` retained | LOW | Fallback for other legacy agents; no longer used by orch |
| AgentSessionService | ⏸ | Audited, not extracted (A0/A1) |
| DistillationService | ⏸ | Audited, not extracted (D0) |
| Vue/Electron migration | ⏸ | Premature; codebase not frozen |

### 10. Next Phase Recommendations

1. **FREEZE the architecture.** The protocol layer and service boundaries are stable and well-tested (203 tests). Do not add new abstractions.

2. **Do NOT extract AgentSessionService or DistillationService.** Both have been audited. The current decomposition is correct.

3. **Do NOT begin Vue/Electron migration.** The codebase is not frozen enough for a frontend rewrite. Wait until `OpenAIOrchestratedAgent` implements `AgentBackend` natively and IM bots are either migrated or removed.

4. **Address `OpenAIOrchestratedAgent` native AgentBackend when ready.** This is the single highest-value remaining item. When done, `ensure_agent_backend()` becomes a no-op for the orchestrator, and `load_agent("openai")` can be unblocked.

5. **Add Streamlit smoke tests when feasible.** A minimal `streamlit run` + `curl` health check would catch import errors and protocol wiring bugs that static tests miss.

## Consequences

- All frontend dispatch is now unified: `ensure_agent_backend(agent) → submit(AgentInput) → AgentOutputChannel → AgentOutputDrainer`.
- Both `GeneraticAgent` and `OpenAIOrchestratedAgent` are native `AgentBackend` implementations.
- `_LegacyAgentAdapter` is retained as a fallback for other `put_task`-only agents. It is no longer used by the orchestrator.
- All new frontend code must use `ensure_agent_backend(dispatch_agent).submit(AgentInput(...))`.
- All new service code must follow the `frontends/services/` constraints (no streamlit, no session_state).
- `put_task()` is deprecated but not removed. Do NOT delete it.
- `__main__` blocks are deprecated but not removed. Do NOT delete them.
- Phase 7-full and Phase 6-full are intentionally not marked Done.
- 623 tests passed, 0 failed, 0 skipped.
