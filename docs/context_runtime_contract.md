# Context Runtime — Data Contracts & Test Plan (v2)

> Phase 1 deliverable. Revised per 10-constraint review. Frozen before implementation.

---

## 0. Boundaries & Acceptance Criteria

### In scope

1. Detect cwd, git root, branch, remote, dirty files → `WorkspaceSnapshot`
2. Generate stable `project_id` + key files list → `ProjectIdentity`
3. Generate `session_id`, track process metadata → `RuntimeIdentity`
4. Persist session/task state via existing `MemoryStore` (SQLite)
5. Unified memory read facade (`reader.py`) — reads L1, L2, structured, session, task
6. `context_builder.py` — pure constructor, consumes ONLY typed dataclasses, never reads files/DB
7. Preview mode: log packet to disk, do NOT inject
8. Route-gated inject: only non-chat routes get context injected
9. Turn-end compactor: lightweight summary + task_state update (no extra LLM call)
10. Classic executor bridge: lightweight workspace_block extension

### Out of scope

- Modifying `agent_loop.py` or `ga.py`
- Taking over L1/L2 primary prompt retrieval
- Replacing `get_global_memory()`
- Large dependency additions
- Full conversation summarization via LLM
- Visual/UI changes
- Auto-promoting candidates to durable memory_items

### Acceptance criteria

1. `WorkspaceProbe.probe()` returns correct git/cwd info for any directory
2. `project_id` is stable across restarts for same project root
3. Switching directories → different `project_id`, no cross-contamination
4. `MemoryReader` returns blocks from L1, L2, structured, session, task via unified interface
5. `ContextPacket` is under max_chars limit, includes source metadata
6. Default mode is `preview` (log only), default enabled is `0` (off)
7. Chat route gets NO project context injected
8. Turn-end compactor writes to `task_state` table + `memory_candidates`, NOT to L1/L2
9. All writes go through `MemoryWriteGate`
10. Legacy global memory still readable and unchanged
11. Structured memory blocks are tagged `source="structured:supplementary"` with lower priority than L1/L2
12. Every runtime module becomes no-op when `GA_CONTEXT_RUNTIME_ENABLED != "1"`

---

## 1. Environment Variables

### 1.1 Variable Table

| Variable | Values | Default | Effect |
|----------|--------|---------|--------|
| `GA_CONTEXT_RUNTIME_ENABLED` | `0`, `1` | `0` | Master kill-switch. `0` = all modules are no-op. |
| `GA_CONTEXT_RUNTIME_MODE` | `off`, `preview`, `inject` | `preview` | `off`=no probe/build/inject; `preview`=probe+build+log; `inject`=probe+build+inject(route-gated) |
| `GA_CONTEXT_PACKET_MAX_CHARS` | integer | `4000` | Hard cap on assembled ContextPacket serialized length |
| `GA_CONTEXT_MEMORY_MAX_CHARS` | integer | `2000` | Cap on sum of memory block chars within packet |
| `GA_CONTEXT_PREVIEW_DIR` | path | `temp/context_previews/` | Where preview JSON is written (relative to PROJECT_ROOT) |
| `GA_CONTEXT_SESSION_DB` | path | `memory/catalog.sqlite` | SQLite db path for session/task state (relative to PROJECT_ROOT) |

### 1.2 Enable Guard (enforced by every module)

```python
# Every core/context/*.py module __init__ or factory function MUST check:
def _enabled() -> bool:
    return os.environ.get("GA_CONTEXT_RUNTIME_ENABLED", "0") == "1"
```

When `_enabled()` returns `False`:
- `WorkspaceProbe.probe()` → returns `None`
- `ProjectIdentity.detect()` → returns `None`
- `RuntimeIdentity.current()` → returns `None`
- `SessionStore` methods → return `None` / empty lists
- `ContextBuilder.build()` → returns `None`
- `Compactor.compact()` → returns `None`

### 1.3 Authority Order

```
1. GA_CONTEXT_RUNTIME_ENABLED=0
   → ALL modules no-op. No probe, no read, no build, no inject, no compact.
   → Irrespective of GA_CONTEXT_RUNTIME_MODE value.

2. GA_CONTEXT_RUNTIME_ENABLED=1 + GA_CONTEXT_RUNTIME_MODE=off
   → No workspace probe. No context build. No injection. No compaction.
   → Session/task store is still writable (for future use).
   → MemoryReader still works (read-only, no side effects).

3. GA_CONTEXT_RUNTIME_ENABLED=1 + GA_CONTEXT_RUNTIME_MODE=preview
   → Probe workspace + project + runtime identity.
   → Build ContextPacket (full assembly).
   → Write ContextPacket JSON to preview_dir.
   → Log: [CONTEXT:PREVIEW] run_id=... route=... chars=... sources=...
   → Do NOT inject into agent prompt.

4. GA_CONTEXT_RUNTIME_ENABLED=1 + GA_CONTEXT_RUNTIME_MODE=inject
   → Probe workspace + project + runtime identity.
   → Build ContextPacket (full assembly).
   → Inject into agent prompt (route-gated, see §4).
   → Log: [CONTEXT:INJECT] run_id=... route=... chars=... sources=...
   → Also write preview JSON (for audit).
```

---

## 2. Data Contracts

### 2.1 `WorkspaceSnapshot`

```python
@dataclass
class WorkspaceSnapshot:
    """Point-in-time snapshot of the current working directory environment."""

    cwd: str                          # os.getcwd() resolved absolute
    git_root: str | None              # git rev-parse --show-toplevel, None if not a repo
    git_branch: str | None            # git branch --show-current
    git_remote_url: str | None        # git remote get-url origin (first remote)
    has_uncommitted_changes: bool     # True if git status --porcelain is non-empty
    dirty_files: list[str]            # changed file paths relative to git_root, capped at 30
    detected_at: float                # time.time()

    # Invariants
    # - git_root is None OR cwd.startswith(git_root)
    # - len(dirty_files) <= 30
```

### 2.2 `ProjectIdentity`

```python
@dataclass
class ProjectIdentity:
    """Stable identity of the project at the current workspace root."""

    project_id: str                   # sha256(git_root or cwd)[:12], deterministic
    project_name: str                 # os.path.basename(project_root)
    project_root: str                 # git_root if available, else cwd
    key_files: list[str]              # top-level config files, capped at 20
    languages: list[str]              # detected from key_file extensions only
    generated_at: float               # time.time()

    # Invariants
    # - project_id is deterministic: same absolute path → same id
    # - len(key_files) <= 20
```

### 2.3 `RuntimeIdentity`

```python
@dataclass
class RuntimeIdentity:
    """Identity of the running agent process / session."""

    session_id: str                   # "sess_" + uuid4().hex[:12], stable for process lifetime
    process_id: int                   # os.getpid()
    agent_backend: str                # "genericagent" | "openai-agents"
    hostname: str                     # socket.gethostname()
    started_at: float                 # session start time (time.time())
    env_summary: dict[str, str]       # GA_CONTEXT_* env vars only, values truncated to 80 chars

    # Invariants
    # - session_id is stable for the lifetime of the process
    # - env_summary keys are all uppercase, prefixed with GA_CONTEXT_
```

### 2.4 `TaskState`

```python
@dataclass
class TaskState:
    """Persistent state of a single agent task (one put_task invocation)."""

    task_id: str                      # uuid4().hex
    run_id: str                       # backend run_id
    status: str                       # "pending" | "running" | "completed" | "aborted" | "error"
    summary: str                      # one-line description, max 200 chars
    source: str                       # "user" | "feishu" | "autonomous" | "task"
    parent_session_id: str            # FK to SessionRecord.session_id
    project_id: str                   # FK to ProjectIdentity.project_id
    started_at: float | None
    completed_at: float | None
    exit_reason: str | None           # "completed" | "aborted" | "error" | "early_stop" | "direct_answer"
    turn_count: int                   # from handler.current_turn
    tool_count: int                   # count of tool calls made

    # Invariants
    # - status in {"pending", "running", "completed", "aborted", "error"}
    # - started_at is not None if status != "pending"
    # - completed_at is not None if status in {"completed", "aborted", "error"}
    # - len(summary) <= 200
```

### 2.5 `SessionRecord`

```python
@dataclass
class SessionRecord:
    """Persistent record of an agent session. One per process lifetime."""

    session_id: str                   # matches RuntimeIdentity.session_id
    project_id: str                   # matches ProjectIdentity.project_id at session start
    started_at: float
    ended_at: float | None            # None if session is still active
    last_active_at: float             # updated on each task start/end
    task_count: int                   # total tasks run in this session
    current_active_task_id: str | None
    last_completed_task_id: str | None
```

### 2.6 `MemoryBlock`

```python
@dataclass
class MemoryBlock:
    """A scoped chunk of memory retrieved from any memory source."""

    source: str                       # "L1" | "L2" | "structured:supplementary" | "session" | "task"
    source_priority: str              # "primary" (L1, L2) | "supplementary" (structured) | "volatile" (session, task)
    source_path: str | None           # file path or db reference
    content: str                      # the actual text
    relevance_score: float            # 0.0 - 1.0
    chars: int                        # len(content)
    metadata: dict                    # source-specific metadata

    # Invariants
    # - source in {"L1", "L2", "structured:supplementary", "session", "task"}
    # - source_priority in {"primary", "supplementary", "volatile"}
    # - L1/L2 ALWAYS have source_priority="primary"
    # - structured memory ALWAYS has source_priority="supplementary"
    # - session/task ALWAYS have source_priority="volatile"
    # - 0.0 <= relevance_score <= 1.0
    # - sorted by (source_priority DESC, relevance_score DESC) in ContextPacket
```

### 2.7 `MemoryBundle`

```python
@dataclass
class MemoryBundle:
    """Pre-assembled memory blocks from MemoryReader. Passed to ContextBuilder."""

    blocks: list[MemoryBlock]
    total_chars: int                  # sum(len(b.content) for b in blocks)
    source_counts: dict[str, int]     # {"L1": 1, "L2": 2, "structured:supplementary": 3, ...}
    queried_at: float

    # Invariants
    # - blocks sorted by (source_priority DESC, relevance_score DESC)
    # - L1/L2 are always included (they are the primary retrieval path)
    # - structured blocks are supplementary — added only if there is budget remaining
```

### 2.8 `ContextPacket`

```python
@dataclass
class ContextPacket:
    """The assembled context. Built by ContextBuilder from typed inputs ONLY."""

    # Identity blocks (from probes)
    workspace: WorkspaceSnapshot | None
    project: ProjectIdentity | None
    runtime: RuntimeIdentity | None

    # State blocks (from SessionStore)
    current_session: SessionRecord | None
    last_active_task: TaskState | None
    active_tasks: list[TaskState]

    # Memory blocks (from MemoryBundle — NOT direct file/DB read)
    memory_bundle: MemoryBundle | None

    # Metadata (mandatory)
    generated_at: float
    total_chars: int                  # serialized length
    source_breakdown: dict[str, int]  # chars per source: {"workspace": N, "project": N, "memory": N, ...}
    policy_mode: str                  # "off" | "preview" | "inject"
    target_route: str | None          # code / review / research / executor / planner_executor / None
    max_chars_limit: int              # the limit that was enforced

    # Invariants
    # - total_chars <= max_chars_limit
    # - ContextBuilder consumes ONLY: WorkspaceSnapshot, ProjectIdentity, RuntimeIdentity,
    #   SessionRecord, TaskState, MemoryBundle — never files, DB connections, or raw strings
    # - memory_bundle.blocks are pre-sorted by MemoryReader
```

### 2.9 `CompactionEvent`

```python
@dataclass
class CompactionEvent:
    """Lightweight turn-end summary. No extra LLM call. Reads ONLY response text +
    handler.working['key_info'] + existing task_state. Does NOT read L1/L2."""

    run_id: str
    turn_index: int
    summary: str                      # from <summary> tag or first non-empty response line, max 300 chars
    decisions: list[str]              # tool names + truncated args this turn
    task_progress: str | None         # from handler.working['key_info'] or previous task summary
    blockers: list[str]               # error indicators from response
    next_action: str | None           # from exit_reason or next_prompt hint
    durable_facts: list[str]          # candidate facts, max 5, each max 200 chars
    compacted_at: float

    # Invariants
    # - len(summary) <= 300
    # - len(durable_facts) <= 5
    # - Does NOT read L1/L2 files
    # - Does NOT invoke an extra LLM call
    # - durable_facts written as memory_candidates with source="compactor"
    # - NEVER auto-promotes to memory_items (requires manual/promoter action)
    # - task_state update goes through SessionStore (writes to task_state table, not global_mem)
```

---

## 3. Memory Reader Unified Facade

### 3.1 Contract

```python
class MemoryReader:
    """
    Unified read-only facade for all memory sources.
    context_builder MUST consume pre-built MemoryBundle from this reader.
    NEVER reads files or DB directly.
    """

    def __init__(self, project_root: str | None = None, db_path: str | None = None): ...

    # Legacy memory (ALWAYS available, not gated)
    def read_global_memory(self) -> dict[str, str]:
        """Returns {l1: str, l2: str}. L1 and L2 are the PRIMARY retrieval path."""
        ...

    # Structured memory (gated by GA_CONTEXT_RUNTIME_ENABLED=1)
    def read_structured_memory(self, query: str, limit: int = 5) -> list[MemoryBlock]:
        """
        Returns blocks tagged source='structured:supplementary'.
        ALWAYS supplementary priority — never replaces L1/L2.
        Returns empty list when GA_CONTEXT_RUNTIME_ENABLED != '1'.
        """
        ...

    # Session / task state (gated by GA_CONTEXT_RUNTIME_ENABLED=1)
    def read_session_state(self, session_id: str) -> SessionRecord | None: ...
    def read_task_state(self, task_id: str) -> TaskState | None: ...
    def read_active_tasks(self, project_id: str) -> list[TaskState]: ...
    def read_session_history(self, session_id: str, limit: int = 10) -> list[MemoryBlock]: ...

    # Unified scoped query — the primary entry point for ContextBuilder
    def scoped_query(
        self,
        user_query: str,
        project_id: str | None = None,
        session_id: str | None = None,
        max_chars: int = 2000,
    ) -> MemoryBundle:
        """
        Assembles a MemoryBundle from ALL sources, respecting priority order:
        1. L1 (primary) — always included if content matches query keywords
        2. L2 (primary) — always included if content matches query keywords
        3. structured (supplementary) — included only if budget remains after L1+L2
        4. session/task (volatile) — included only if budget remains

        Returns MemoryBundle with blocks sorted by (source_priority DESC, relevance_score DESC).
        """
        ...
```

### 3.2 Source Priority Order (hard rule)

```
1. L1 (global_mem_insight.txt)        → source_priority = "primary"
2. L2 (global_mem.txt)                → source_priority = "primary"
3. structured (SQLite FTS5)           → source_priority = "supplementary"
4. session (session_history)          → source_priority = "volatile"
5. task (active/completed task_state) → source_priority = "volatile"
```

L1 + L2 are ALWAYS included first. Structured memory fills the remaining budget. Volatile sources are last.

This ensures structured memory CANNOT accidentally take over primary prompt retrieval.

---

## 4. Context Builder (Pure Constructor)

### 4.1 Contract

```python
class ContextBuilder:
    """
    Pure constructor. Takes typed dataclasses, returns ContextPacket.
    NEVER reads files. NEVER reads SQLite. NEVER reads global memory directly.
    """

    def __init__(
        self,
        *,
        max_chars: int = 4000,
        policy_mode: str = "preview",
    ): ...

    def build(
        self,
        *,
        workspace: WorkspaceSnapshot | None,
        project: ProjectIdentity | None,
        runtime: RuntimeIdentity | None,
        session: SessionRecord | None,
        memory_bundle: MemoryBundle | None,
        target_route: str | None,
    ) -> ContextPacket | None:
        """
        Returns None if:
        - policy_mode == "off"
        - target_route == "chat" or target_route is None
        - all inputs are None

        Returns ContextPacket respecting max_chars limit.
        Truncation order: volatile memory first, then supplementary, then state blocks.
        Identity blocks (workspace, project, runtime) are NEVER truncated — they are small.
        """
        ...

    def serialize(self, packet: ContextPacket) -> str:
        """Render ContextPacket to the injection text format."""
        ...
```

### 4.2 Truncation Priority (when over max_chars)

```
Keep (never truncate):
  1. [CONTEXT PACKET] header + metadata line
  2. Workspace block (cwd, git_root, branch — tiny)
  3. Project block (project_id, name, key_files — tiny)

Truncate in order (first to go):
  4. Volatile memory blocks (session, task)
  5. Supplementary memory blocks (structured)
  6. State blocks (active_tasks list)
  7. Individual memory block content (truncated with "…")

Never truncate:
  - L1/L2 primary memory blocks (they are authoritative)
  - Identity blocks (workspace, project, runtime)
```

---

## 5. Injection Rules

### 5.1 Route Gating Matrix

| Route | Inject? | Content Budget |
|-------|:---:|------|
| `chat` | **NO** | 0 chars — no context at all |
| `code` | YES | workspace (100) + project (100) + memory (1500) |
| `review` | YES | workspace (100) + project (100) + last_active_task (200) + memory (1500) |
| `research` | YES | workspace (100) + project (100) + memory (2500) — larger memory budget |
| `executor` | YES | FULL: workspace + project + session + active_tasks + all memory (up to max_chars) |
| `planner_executor` | YES | FULL: same as executor |
| `None` (undetected) | **NO** | 0 chars — ambiguous routing, safe default |

### 5.2 Injection Format

```
[CONTEXT PACKET — {policy_mode} mode, {total_chars} chars, route={target_route}]

## Workspace
cwd: {cwd}
git_root: {git_root}
branch: {git_branch}
dirty: {has_uncommitted_changes}

## Project
project_id: {project_id}
name: {project_name}
root: {project_root}
key_files: {key_files_str}

## Current State
session: {session_id} ({task_count} tasks)
last_active_task: {summary} [{status}]
active_tasks: {count}

## Relevant Memory
{for each block in memory_bundle.blocks:}
[{source} | priority={source_priority} | score={relevance_score}]
{content}
...

[/CONTEXT PACKET]
```

### 5.3 Default Mode

- `GA_CONTEXT_RUNTIME_ENABLED` defaults to `0` → everything off
- `GA_CONTEXT_RUNTIME_MODE` defaults to `preview` → if enabled, logs but doesn't inject
- User must explicitly set `GA_CONTEXT_RUNTIME_ENABLED=1` AND `GA_CONTEXT_RUNTIME_MODE=inject` to get injection
- Chat route NEVER receives context even in inject mode

---

## 6. Turn-End Compactor Constraints

### 6.1 What the Compactor Reads

| Source | Allowed? | Purpose |
|--------|:---:|------|
| Response text (from agent_loop yield) | YES | Extract `<summary>`, decisions, errors |
| `handler.working['key_info']` | YES | Task progress context |
| `handler.current_turn` | YES | Turn index |
| `handler.history_info` (last 5 entries) | YES | Recent summary context |
| Existing `TaskState` from SessionStore | YES | Previous task state to update |
| L1 (`global_mem_insight.txt`) | **NO** | Compactor must NOT read L1 |
| L2 (`global_mem.txt`) | **NO** | Compactor must NOT read L2 |
| SQLite `memory_items` | **NO** | Compactor must NOT read durable memory |
| Other SOP files in `memory/` | **NO** | Compactor is not an agent |

### 6.2 What the Compactor Writes

| Target | Allowed? | Source tag | Gate |
|--------|:---:|------|------|
| `TaskState` via SessionStore | YES | — | SessionStore internal |
| `memory_candidates` | YES | `"compactor"` | Passes `MemoryWriteGate` |
| `memory_items` | **NO** | — | BLOCKED by write gate for source="compactor" |
| L1/L2 files | **NO** | — | Never touched |
| `evidence_chunks` | NO (Phase 1) | — | Phase N+1 |

### 6.3 Compaction Logic (zero LLM overhead)

```python
def compact(response_text: str, handler_working: dict, task_state: TaskState | None) -> CompactionEvent:
    # 1. Extract <summary>...</summary> from response_text (regex)
    # 2. If no <summary> tag: use first non-empty line of response (max 300 chars)
    # 3. Extract tool call names from response_text (regex for tool_name patterns)
    # 4. Pull task_progress from handler_working.get('key_info', '')
    # 5. Check for error/blocked indicators in response_text
    # 6. Extract durable_facts: any lines with "关键" / "重要" / "note:" / verified patterns
    # 7. Build CompactionEvent (NO LLM call)
    # 8. Write TaskState update via SessionStore
    # 9. Write durable_facts as memory_candidates (source="compactor")
    return event
```

---

## 7. Test Plan

### Phase 2 — Workspace / Project / Runtime Identity

**File**: `tests/unit/test_workspace_probe.py`

| Test | Verifies |
|------|----------|
| `test_probe_cwd_absolute` | cwd is absolute path |
| `test_probe_git_root_detected` | git_root found when in a repo |
| `test_probe_git_branch` | branch name returned |
| `test_probe_no_git_outside_repo` | git_root=None, no crash |
| `test_probe_dirty_files_capped` | len(dirty_files) ≤ 30 |
| `test_probe_disabled_when_env_off` | returns None when GA_CONTEXT_RUNTIME_ENABLED!=1 |

**File**: `tests/unit/test_project_identity.py`

| Test | Verifies |
|------|----------|
| `test_project_id_stable` | Same abs path → same project_id |
| `test_project_id_different_paths` | Different path → different project_id |
| `test_key_files_python_detected` | Finds pyproject.toml, requirements.txt |
| `test_key_files_js_detected` | Finds package.json, tsconfig.json |
| `test_languages_from_extensions` | Key file extensions → language list |
| `test_disabled_when_env_off` | detect() returns None |

**File**: `tests/unit/test_runtime_identity.py`

| Test | Verifies |
|------|----------|
| `test_session_id_stable_within_process` | Same process → same session_id |
| `test_session_id_format` | Starts with "sess_" |
| `test_env_filter_only_ga_context` | Only GA_CONTEXT_* vars captured |
| `test_env_values_truncated` | Values truncated to 80 chars |
| `test_disabled_when_env_off` | current() returns None |

### Phase 3 — Session / Task Persistence

**File**: `tests/unit/test_session_store.py`

| Test | Verifies |
|------|----------|
| `test_session_crud` | Create → read → update → end session |
| `test_task_state_crud` | Create → read → update status → query by project_id |
| `test_active_tasks_filter` | Query tasks by (project_id, status="running") |
| `test_cross_project_isolation` | Different project_id → disjoint result sets |
| `test_disabled_when_env_off` | Store methods return None |

**File**: `tests/unit/test_task_state.py`

| Test | Verifies |
|------|----------|
| `test_task_lifecycle` | pending → running → completed state transitions |
| `test_task_summary_truncation` | len(summary) ≤ 200 |
| `test_task_timestamps` | started_at set on running, completed_at set on terminal |

### Phase 4 — Memory Reader Facade

**File**: `tests/unit/test_memory_reader.py`

| Test | Verifies |
|------|----------|
| `test_read_global_memory_returns_l1_l2` | L1 and L2 content from text files |
| `test_read_structured_returns_supplementary` | Blocks tagged "structured:supplementary" |
| `test_read_structured_empty_when_disabled` | Returns [] when enabled=0 |
| `test_scoped_query_respects_priority_order` | L1/L2 before structured before volatile |
| `test_scoped_query_respects_max_chars` | Total chars ≤ max_chars |
| `test_memory_bundle_sorted` | Blocks sorted by (priority DESC, score DESC) |
| `test_read_session_state` | SessionRecord retrieved correctly |
| `test_read_task_state` | TaskState retrieved correctly |

### Phase 5 — Context Builder (Pure Constructor)

**File**: `tests/unit/test_context_builder.py`

| Test | Verifies |
|------|----------|
| `test_build_returns_none_for_chat_route` | Chat → None |
| `test_build_returns_none_for_none_route` | Undetected route → None |
| `test_build_code_route_includes_workspace_project_memory` | Correct subset |
| `test_build_executor_route_includes_full_packet` | All blocks present |
| `test_build_respects_max_chars` | total_chars ≤ max_chars_limit |
| `test_build_truncation_order` | Volatile truncated before supplementary before primary |
| `test_build_preview_mode_has_correct_metadata` | policy_mode="preview" in packet |
| `test_build_inject_mode_has_correct_metadata` | policy_mode="inject" |
| `test_build_off_mode_returns_none` | policy_mode="off" → None |
| `test_serialize_produces_valid_format` | Has [CONTEXT PACKET] header and footer |
| `test_source_breakdown_accurate` | Char counts per source are correct |
| `test_builder_never_reads_files` | No file I/O in builder code (verified by mock injection) |

### Phase 6 — Integration: Preview Mode

**File**: `tests/integration/test_context_runtime_preview.py`

| Test | Verifies |
|------|----------|
| `test_full_pipeline_preview` | probe → reader → builder → JSON file written |
| `test_preview_json_valid` | JSON is parseable, contains all expected fields |
| `test_preview_no_injection_in_prompt` | Agent prompt does NOT contain context packet |
| `test_legacy_memory_unchanged` | L1/L2 files untouched after pipeline run |
| `test_directory_switch_isolation` | Different cwd → different project_id in preview |
| `test_disabled_by_default` | When enabled=0, no preview file written |

### Phase 7 — Integration: Injection Mode

**File**: `tests/integration/test_context_runtime_injection.py`

| Test | Verifies |
|------|----------|
| `test_inject_into_code_route` | Code route prompt contains workspace + project |
| `test_no_inject_into_chat_route` | Chat route prompt does NOT contain context packet |
| `test_inject_respects_max_chars` | Injected text ≤ max_chars |
| `test_session_resume_sees_previous_task` | Task 2 context includes Task 1 state |
| `test_structured_memory_supplementary_only` | Structured blocks tagged supplementary, not primary |
| `test_l1_l2_still_injected_via_global_memory` | Legacy injection path still works |

### Phase 8 — Turn-End Compactor

**File**: `tests/unit/test_compactor.py`

| Test | Verifies |
|------|----------|
| `test_extract_summary_from_tag` | Finds `<summary>` in response text |
| `test_fallback_summary_no_tag` | Uses first non-empty line |
| `test_extract_tool_decisions` | Tool names from response |
| `test_durable_facts_capped` | len(durable_facts) ≤ 5 |
| `test_writes_to_memory_candidates_only` | Source="compactor", target=candidates |
| `test_never_writes_to_memory_items` | Write gate blocks source="compactor" → memory_items |
| `test_never_reads_l1_l2` | No file I/O to global_mem files |
| `test_updates_task_state` | TaskState status/summary updated after compaction |
| `test_disabled_when_env_off` | compact() returns None |

---

## 8. Rollback Plan

### Per-phase rollback

Each phase adds to `core/context/` directory. To rollback any phase:
1. Delete the specific module file(s) from `core/context/`
2. Revert any wiring changes (one-line injection additions in `openai_agentmain.py`)
3. Environment variables are no-op by default (`GA_CONTEXT_RUNTIME_ENABLED=0`)

### Full rollback

```bash
rm -rf core/context/
git checkout core/openai_agentmain.py core/memory/reader.py
```

### Safe writes guarantee

| Write target | Modifies existing data? | Reversible? |
|-------------|:---:|:---:|
| Preview JSON files (`temp/context_previews/`) | Append-only | Delete directory |
| `memory/catalog.sqlite` session/task tables | New rows in separate tables | Delete DB rows or DB file |
| `memory_candidates` (compactor) | New rows | Delete rows |
| L1/L2 text files | **NEVER touched** | N/A |
| `memory_items` (durable) | **NEVER touched by runtime** | N/A |

---

## 9. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Enabled + Mode as separate vars | Enabled=0 is a hard kill-switch; Mode controls what happens when enabled |
| Default enabled=0, mode=preview | No surprise behavior; user must explicitly opt in to both |
| Structured memory ALWAYS supplementary | Prevents accidental takeover of primary prompt retrieval |
| Compactor never reads L1/L2 | Compactor is not an agent; it shouldn't interpret global memory |
| Compactor never auto-promotes | Durable memory requires human or promoter action; compactor only suggests |
| ContextBuilder pure constructor | Injectable dependencies → testable with mocks → no file I/O in tests |
| Chat route always excluded | 4000 chars of project context in casual chat is user-hostile |
| Classic path = workspace_block only | `agent_loop.py` is the deepest kernel; touching it risks everything |

---

## 10. Phase Execution Order

```
Phase 2  → workspace_probe + project_identity + runtime_identity + unit tests
Phase 3  → session_store + task_state persistence + unit tests
Phase 4  → memory reader facade (unified read) + unit tests
Phase 5  → context_builder (pure constructor) + unit tests
Phase 6  → integration: preview mode (full pipeline, no injection)
Phase 7  → integration: injection mode (route-gated, OpenAI Agents only)
Phase 8  → turn-end compactor + unit tests
Phase 9  → classic executor handoff bridge (workspace_block extension)
Phase 10 → full integration test suite
Phase 11 → env var documentation + rollback guide
```

---

## Next: Phase 2

Implement `core/context/workspace_probe.py`, `project_identity.py`, `runtime_identity.py` with unit tests. No injection wiring. Each module checks `GA_CONTEXT_RUNTIME_ENABLED` at entry.
