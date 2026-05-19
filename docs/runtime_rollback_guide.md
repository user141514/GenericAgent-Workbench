# Runtime Rollback Guide

## Goal

This guide lists exactly what was added or changed for the runtime-upgrade pass so you can verify or roll back without guessing.

## Additive Files

These files are purely additive. Rolling them back means deleting them:

- `core/runtime/event_schema.py`
- `core/runtime/event_log.py`
- `core/runtime/session.py`
- `core/runtime/state_machine.py`
- `core/runtime/host.py`
- `tests/unit/test_runtime_state_machine.py`
- `tests/unit/test_runtime_host.py`
- `docs/runtime_implementation_change_log.md`
- `docs/runtime_rollback_guide.md`
- `docs/runtime_final_result.md`

## Modified Integration Files

These files were edited in place. Rolling them back means restoring their pre-upgrade diff:

- `core/openai_agentmain.py`
  Runtime host initialization and execution-loop wiring.
- `core/router_rules.py`
  Route result contract now includes `mode` and `parallel_subtasks`.
- `core/context/session_store.py`
  Session snapshot table and CRUD.
- `core/context/memory_reader.py`
  Memory-plane read-side and session snapshot read support.
- `core/runtime/__init__.py`
  Export surface for new runtime primitives.
- `tests/unit/test_agent_graph.py`
  Updated to the real runtime graph contract.
- `tests/unit/test_dynamic_graph.py`
  Updated to the real runtime graph contract.
- `tests/unit/test_memory_reader.py`
  Added snapshot and memory-plane assertions.
- `tests/unit/test_router_rules.py`
  Added route-mode assertions.
- `tests/unit/test_session_store.py`
  Added snapshot assertions.

## Recommended Rollback Order

1. Revert `core/openai_agentmain.py`.
   This detaches the live runtime loop from the new host.
2. Revert `core/router_rules.py`.
   This removes explicit `single_agent` and `multi_agent` routing metadata.
3. Revert `core/context/session_store.py` and `core/context/memory_reader.py`.
   This removes snapshot persistence and memory-plane read integration.
4. Revert `core/runtime/__init__.py`.
   This drops the new runtime exports.
5. Delete the additive runtime files and their tests.
6. Revert the updated tests if you want the repository to validate the legacy contract again.

## Verification After Rollback

After rollback, the fastest checks are:

```powershell
python -m pytest tests/unit/test_agent_graph.py tests/unit/test_dynamic_graph.py tests/unit/test_router_rules.py -q
python -m pytest tests/unit/test_session_store.py tests/unit/test_memory_reader.py -q
```

If you keep the new tests, they should fail after rollback. That is expected because they validate the upgraded runtime contract.
