# Runtime Mode And Memory Plan

Date: 2026-05-06
Workspace: `F:\GAgent-Multi`

## Phase 1: Route Contract And Mode Split

Status: in progress, first implementation pass landed.

Goals:

- keep one user entry
- return a formal route contract with:
  - `target`
  - `mode`
  - `parallel_subtasks`
- separate execution paths clearly:
  - `single_agent` -> `planner_executor`
  - `multi_agent` -> `task_router`

Done in this pass:

- extended `RouteResult`
- added conservative `mode` derivation
- changed orchestrator selection logic to branch by mode
- recorded `execution_mode` in route audit metadata

## Phase 2: Memory Plane Formalization

Goals:

1. `project memory`
   - only verified project facts
   - promotion gated by runtime evidence
2. `session memory`
   - current mode
   - completed / pending work
   - active diagnostics and review status
3. `run memory`
   - recent turns
   - temporary working context
   - disposable task-local artifacts
4. `collaboration memory`
   - only enabled in `multi_agent`
   - shared artifacts between specialists

Required code work:

- add a formal memory-plane contract document or schema
- add explicit ownership rules:
  - router: read-only
  - single-agent executor: run/session writes only
  - multi-agent specialists: collaboration writes only
  - runtime host: only component allowed to promote durable memory

## Phase 3: Session Snapshot

Goals:

- persist enough state to stop and restore safely

Snapshot fields to add:

- `session_id`
- `current_mode`
- `route_target`
- `execution_mode`
- `pending_tool_call`
- `completed_steps`
- `pending_steps`
- `modified_files`
- `diff_refs`
- `diagnostic_refs`
- `review_status`
- `collaboration_artifacts`

## Phase 4: Runtime Governance

Goals:

- move from "mode split exists" to "mode split is governable"

Required modules:

- event log as single source of truth
- tool registry + policy gate
- diagnose-first transition rules
- review verdict before completion

## Verification Checklist

- router still returns stable `target` values for existing callers
- explicit `single_agent` requests resolve to `planner_executor`
- explicit `multi_agent` requests resolve to `task_router`
- parallel subtasks are only triggered inside `multi_agent`
- no ambiguous request bypasses the shared entry point

## Risks

- existing tests may still assume older route-only semantics in some places
- environment drift remains a blocker for broad validation until Python `>=3.10` is used consistently
- memory write governance is still conceptual until host/session policy is added
