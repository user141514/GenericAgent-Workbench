# Runtime Mode And Memory State Snapshot

Date: 2026-05-06
Workspace: `F:\GAgent-Multi`
Focus: split `single_agent` and `multi_agent` under one entry, then formalize memory layering around that split.

## Current State

This pass turns the existing routing layer from "intent only" into "intent + execution mode".

- `core/router_rules.py`
  - `RouteResult` now carries `target`, `mode`, and `parallel_subtasks`.
  - `mode` is conservative by design:
    - `chat` stays `single_agent`
    - explicit parallel subtasks switch to `multi_agent`
    - multiple specialist signals (`code/review/research`) switch to `multi_agent`
    - the rest stay `single_agent`
- `core/openai_agentmain.py`
  - the entry is still unified
  - actual execution now branches by `execution_mode`
    - `single_agent` -> `planner_executor`
    - `multi_agent` -> `task_router`
  - `_force_multi_agent` now overrides mode directly instead of faking a generic route target
  - route audit metadata now records `execution_mode`

## Architecture Reading

The repo already had the raw pieces for both modes, but not a formal split:

- single-agent execution leaf already existed as `planner_executor`
- multi-agent collaboration root already existed as `task_router`
- run-scoped collaboration memory already exists in `core/runtime/shared_store.py`
- read-side memory facade already exists in `core/context/memory_reader.py`

The gap was that routing only produced `target`, while execution selection still collapsed most work back into one executor path. This pass fixes that contract first.

## Memory Positioning

The intended memory layering is now:

1. `project memory`
   - durable project facts and rules
   - read mainly through `MemoryReader`
2. `session memory`
   - session progress, current mode, active task state
   - partially present in `SessionStore`, not complete yet
3. `run memory`
   - transient per-run working context, recent turns, temporary artifacts
4. `collaboration memory`
   - multi-agent-only shared workspace
   - current anchor: `SharedArtifactStore`

## Known Gaps

- session snapshot is not formalized yet
- memory write permissions are not yet governed by runtime policy
- long-term memory promotion still lacks `event log + review verdict` gating
- diagnose / review / recovery are still separate follow-up phases
- current shell Python is still behind repo requirement
  - `pyproject.toml` requires `>=3.10`
  - the active `python` in this shell was previously observed as `3.7.0`

## Next Step Trigger

The next implementation step should be memory formalization, not more prompt work:

- define read/write rules for each memory plane
- extend session snapshot fields
- bind collaboration memory lifecycle to `multi_agent` runs only
- only then continue to stop/restore, review verdict, and event-log recovery
