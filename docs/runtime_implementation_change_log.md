# Runtime Implementation Change Log

## Scope

This change set upgrades the current GenericAgent runtime around four concrete axes:

1. Single-agent and multi-agent execution are now explicit runtime modes, routed from one shared entrypoint.
2. Session snapshot and memory-plane read-side are persisted and recoverable.
3. A real runtime host now records mode, LLM, tool, handoff, review, stop, and recovery events.
4. The OpenAI orchestrated runtime is wired into the new host instead of keeping runtime state as ad hoc local variables.

## Files Added

- `core/runtime/event_schema.py`
  Canonical runtime event structure and event type vocabulary.
- `core/runtime/event_log.py`
  Session-scoped JSONL event log and snapshot writer under `logs/sessions/<session_id>/`.
- `core/runtime/session.py`
  In-memory runtime session state mirrored into persistent snapshots.
- `core/runtime/state_machine.py`
  Runtime mode state machine and legal transition rules.
- `core/runtime/host.py`
  Central runtime control plane for session lifecycle, events, snapshots, stop, restore, review, and failure.
- `tests/unit/test_runtime_state_machine.py`
  State-machine regression coverage.
- `tests/unit/test_runtime_host.py`
  Runtime-host persistence, review, stop, and restore regression coverage.
- `docs/runtime_implementation_change_log.md`
  This file.
- `docs/runtime_rollback_guide.md`
  Manual rollback checklist for this runtime pass.
- `docs/runtime_final_result.md`
  Final implementation summary and architecture diagram.

## Files Updated

- `core/router_rules.py`
  Route decisions now carry `mode` and `parallel_subtasks`, not just `target`.
- `core/openai_agentmain.py`
  The shared entrypoint now:
  routes into `single_agent` or `multi_agent`,
  initializes `RuntimeHost`,
  records route/mode/tool/handoff/review/stop/failure events,
  writes snapshots during real execution,
  and finalizes sessions through review verdicts.
- `core/context/session_store.py`
  Added persistent `SessionSnapshot`, `session_snapshots` table, recovery payload support, and snapshot CRUD.
- `core/context/memory_reader.py`
  Added memory-plane read-side, session snapshot reads, and scoped snapshot injection.
- `core/runtime/__init__.py`
  Exports the new runtime primitives.
- `core/runtime/event_log.py`
  Now preserves persisted event counts across restore so `event_log_position` remains monotonic.
- `tests/unit/test_agent_graph.py`
  Graph assertions now match the real minimal runtime graph and router-driven mode split.
- `tests/unit/test_dynamic_graph.py`
  Dynamic graph assertions now validate runtime mode behavior instead of legacy always-on specialist nodes.
- `tests/unit/test_memory_reader.py`
  Added session snapshot and memory-plane coverage.
- `tests/unit/test_router_rules.py`
  Added route mode contract coverage.
- `tests/unit/test_session_store.py`
  Added snapshot persistence and recovery payload coverage.

## Runtime Behavior Added

- Session start now creates:
  a persisted session record,
  a primary task state,
  `logs/sessions/<session_id>/events.jsonl`,
  and `logs/sessions/<session_id>/snapshot.json`.
- Route application now updates:
  `route_target`,
  `execution_mode`,
  `current_mode`,
  and parallel subtask metadata.
- Tool execution now records:
  `tool_requested`,
  `tool_allowed`,
  `tool_started`,
  `tool_completed` or `tool_failed`,
  and diff events when file changes are reported.
- Handoffs now record:
  `handoff_requested` and `handoff_completed`.
- Review now records:
  `review_started`,
  `review_completed`,
  and final session completion.
- Stop and restore now record:
  `stop_requested`,
  `session_stopped`,
  `session_restored`,
  and a recovery-mode transition.

## Test Evidence

Executed under `rag-env`:

```powershell
python -m pytest tests/unit/test_runtime_state_machine.py tests/unit/test_runtime_host.py tests/unit/test_session_store.py tests/unit/test_memory_reader.py tests/unit/test_agent_graph.py tests/unit/test_dynamic_graph.py tests/unit/test_router_rules.py -q
python -m pytest tests/architecture/test_context_boundaries.py tests/unit/test_executor_backend_sync.py tests/unit/test_agent_comparison.py -q
python -m pytest tests/unit/test_tool_permissions.py -q
```

Observed results:

- `113 passed`
- `35 passed`
- `20 passed`
