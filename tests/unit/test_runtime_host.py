import json

import pytest

from core.runtime.host import RuntimeHost


@pytest.fixture
def runtime_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("GA_CONTEXT_RUNTIME_ENABLED", "1")
    project_root = tmp_path / "project"
    project_root.mkdir()
    db_path = tmp_path / "catalog.sqlite"
    logs_root = project_root / "logs" / "sessions"
    return {
        "project_root": project_root,
        "db_path": db_path,
        "logs_root": logs_root,
    }


def _read_event_types(logs_root, session_id: str) -> list[str]:
    events_path = logs_root / session_id / "events.jsonl"
    with events_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line)["event_type"] for line in handle if line.strip()]


def test_runtime_host_start_session_persists_snapshot_and_events(runtime_fixture):
    host = RuntimeHost(
        project_root=str(runtime_fixture["project_root"]),
        logs_root=str(runtime_fixture["logs_root"]),
        session_db_path=str(runtime_fixture["db_path"]),
        agent_name="unit_test_host",
    )

    session = host.start_session(
        user_intent="Implement runtime event chain",
        source="unit-test",
        session_id="sess_runtime_001",
    )

    assert session.session_id == "sess_runtime_001"
    assert session.current_mode == "idle"

    snapshot = host.store.get_snapshot("sess_runtime_001")
    assert snapshot is not None
    assert snapshot.current_mode == "idle"
    assert snapshot.last_user_intent == "Implement runtime event chain"
    assert snapshot.metadata["status"] == "running"

    task = host.store.get_task("sess_runtime_001:primary")
    assert task is not None
    assert task.status == "running"
    assert task.summary == "Implement runtime event chain"

    event_types = _read_event_types(runtime_fixture["logs_root"], "sess_runtime_001")
    assert event_types[:2] == ["session_started", "user_message_received"]

    snapshot_path = runtime_fixture["logs_root"] / "sess_runtime_001" / "snapshot.json"
    assert snapshot_path.exists()


def test_runtime_host_tracks_route_tool_review_and_completion(runtime_fixture):
    host = RuntimeHost(
        project_root=str(runtime_fixture["project_root"]),
        logs_root=str(runtime_fixture["logs_root"]),
        session_db_path=str(runtime_fixture["db_path"]),
        agent_name="unit_test_host",
    )
    session_id = "sess_runtime_002"

    host.start_session(user_intent="Patch runtime host", session_id=session_id)
    host.apply_route(
        route_target="executor",
        execution_mode="single_agent",
        parallel_subtasks=["inspect failing tests", "apply patch"],
    )
    host.begin_llm_turn(1, selected_agent="planner_executor")
    host.request_tool("apply_patch", risk_level="high")
    host.complete_tool(
        "apply_patch",
        result_summary="patched runtime host",
        modified_files=["core/runtime/host.py"],
        diff_refs=["diff_001"],
        collaboration_artifacts={"plan.md": {"status": "done"}},
    )
    host.begin_review()
    host.complete_review(verdict="pass_with_warnings", summary="reviewed runtime host")
    host.complete_session(summary="implemented runtime host")

    snapshot = host.store.get_snapshot(session_id)
    assert snapshot is not None
    assert snapshot.current_mode == "completed"
    assert snapshot.modified_files == ["core/runtime/host.py"]
    assert snapshot.diff_refs == ["diff_001"]
    assert snapshot.review_status == "pass_with_warnings"
    assert snapshot.collaboration_artifacts["plan.md"]["status"] == "done"

    task = host.store.get_task(f"{session_id}:primary")
    assert task is not None
    assert task.status == "completed"
    assert task.exit_reason == "completed"

    session_record = host.store.get_session(session_id)
    assert session_record is not None
    assert session_record.current_active_task_id is None
    assert session_record.last_completed_task_id == f"{session_id}:primary"

    event_types = _read_event_types(runtime_fixture["logs_root"], session_id)
    assert "parallel_subtasks_detected" in event_types
    assert "mode_changed" in event_types
    assert "tool_requested" in event_types
    assert "tool_allowed" in event_types
    assert "tool_started" in event_types
    assert "diff_generated" in event_types
    assert "diff_applied" in event_types
    assert "tool_completed" in event_types
    assert "review_started" in event_types
    assert "review_completed" in event_types
    assert event_types[-1] == "session_completed"
    assert snapshot.event_log_position == len(event_types)


def test_runtime_host_stop_and_restore_enters_recovery_mode(runtime_fixture):
    session_id = "sess_runtime_003"
    host = RuntimeHost(
        project_root=str(runtime_fixture["project_root"]),
        logs_root=str(runtime_fixture["logs_root"]),
        session_db_path=str(runtime_fixture["db_path"]),
        agent_name="unit_test_host",
    )

    host.start_session(user_intent="Resume multi-agent task", session_id=session_id)
    host.apply_route(route_target="executor", execution_mode="multi_agent")
    host.request_tool("run_genericagent_executor", risk_level="high")
    host.request_stop(reason="unit-test-stop")

    stopped_snapshot = host.store.get_snapshot(session_id)
    assert stopped_snapshot is not None
    assert stopped_snapshot.current_mode == "stopped"
    assert stopped_snapshot.pending_tool_call == "run_genericagent_executor"
    assert stopped_snapshot.metadata["status"] == "stopped"

    task = host.store.get_task(f"{session_id}:primary")
    assert task is not None
    assert task.status == "aborted"

    restored_host = RuntimeHost(
        project_root=str(runtime_fixture["project_root"]),
        logs_root=str(runtime_fixture["logs_root"]),
        session_db_path=str(runtime_fixture["db_path"]),
        agent_name="unit_test_host",
    )
    restored = restored_host.restore_session(session_id)

    assert restored is not None
    assert restored.current_mode == "recovery"
    assert restored.execution_mode == "multi_agent"
    assert restored.route_target == "executor"
    assert restored.pending_tool_call == "run_genericagent_executor"

    recovery_snapshot = restored_host.store.get_snapshot(session_id)
    assert recovery_snapshot is not None
    assert recovery_snapshot.current_mode == "recovery"

    event_types = _read_event_types(runtime_fixture["logs_root"], session_id)
    assert "stop_requested" in event_types
    assert "session_stopped" in event_types
    assert "session_restored" in event_types
    assert event_types[-2:] == ["session_restored", "mode_changed"]
