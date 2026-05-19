"""Phase 3a: SessionStore unit tests."""
import os
import pytest
import tempfile
import time
from core.context.session_store import SessionStore, SessionRecord, SessionSnapshot, TaskState


@pytest.fixture
def store():
    """Create a SessionStore with a temp database."""
    os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    s = SessionStore(db_path=path)
    yield s
    os.unlink(path)
    os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)


class TestSessionCRUD:
    """Create → read → update → end session."""

    def test_create_and_get_session(self, store):
        session_id = "sess_test_001"
        rec = store.create_session(session_id, "proj_abc123")
        assert rec is not None
        assert rec.session_id == session_id
        assert rec.project_id == "proj_abc123"
        assert rec.task_count == 0
        assert rec.ended_at is None

        # Read back
        got = store.get_session(session_id)
        assert got is not None
        assert got.session_id == session_id
        assert got.project_id == "proj_abc123"

    def test_update_session(self, store):
        session_id = "sess_test_002"
        store.create_session(session_id, "proj_xyz")
        rec = store.get_session(session_id)
        assert rec is not None

        rec.task_count = 5
        rec.current_active_task_id = "task_001"
        updated = store.update_session(rec)
        assert updated is not None
        assert updated.task_count == 5

        got = store.get_session(session_id)
        assert got is not None
        assert got.task_count == 5
        assert got.current_active_task_id == "task_001"

    def test_end_session(self, store):
        session_id = "sess_test_003"
        store.create_session(session_id, "proj_end")
        rec = store.get_session(session_id)
        rec.ended_at = time.time()
        store.update_session(rec)

        got = store.get_session(session_id)
        assert got is not None
        assert got.ended_at is not None

    def test_get_nonexistent_session(self, store):
        got = store.get_session("nonexistent")
        assert got is None


class TestTaskCRUD:
    """Create → read → update → query tasks."""

    def test_create_and_get_task(self, store):
        task = TaskState(
            task_id="task_001",
            run_id="run_aaa",
            status="running",
            summary="Implement auth middleware",
            parent_session_id="sess_001",
            project_id="proj_abc",
            started_at=time.time(),
        )
        created = store.create_task(task)
        assert created is not None

        got = store.get_task("task_001")
        assert got is not None
        assert got.status == "running"
        assert got.summary == "Implement auth middleware"

    def test_update_task_status(self, store):
        task = TaskState(
            task_id="task_002",
            run_id="run_bbb",
            status="running",
            parent_session_id="sess_001",
            project_id="proj_abc",
            started_at=time.time(),
        )
        store.create_task(task)

        task.status = "completed"
        task.completed_at = time.time()
        task.exit_reason = "completed"
        task.turn_count = 3
        store.update_task(task)

        got = store.get_task("task_002")
        assert got is not None
        assert got.status == "completed"
        assert got.exit_reason == "completed"
        assert got.turn_count == 3

    def test_active_tasks_filter(self, store):
        # Create 3 tasks: 2 running, 1 completed
        for i in range(2):
            store.create_task(TaskState(
                task_id=f"active_{i}",
                run_id=f"run_{i}",
                status="running",
                parent_session_id="sess_001",
                project_id="proj_abc",
                started_at=time.time(),
            ))
        store.create_task(TaskState(
            task_id="done_1",
            run_id="run_done",
            status="completed",
            parent_session_id="sess_001",
            project_id="proj_abc",
            started_at=time.time(),
            completed_at=time.time(),
        ))

        active = store.get_active_tasks(project_id="proj_abc")
        assert len(active) == 2
        assert all(t.status == "running" for t in active)

    def test_cross_project_isolation(self, store):
        store.create_task(TaskState(
            task_id="task_a",
            run_id="run_a",
            status="running",
            parent_session_id="sess_a",
            project_id="proj_alpha",
            started_at=time.time(),
        ))
        store.create_task(TaskState(
            task_id="task_b",
            run_id="run_b",
            status="running",
            parent_session_id="sess_b",
            project_id="proj_beta",
            started_at=time.time(),
        ))

        assert len(store.get_active_tasks(project_id="proj_alpha")) == 1
        assert len(store.get_active_tasks(project_id="proj_beta")) == 1
        assert len(store.get_active_tasks(project_id="proj_gamma")) == 0

    def test_get_last_completed_task(self, store):
        # Create completed tasks at different times
        t1 = time.time()
        store.create_task(TaskState(
            task_id="old_task", run_id="run_old", status="completed",
            parent_session_id="sess_001", project_id="proj_abc",
            started_at=t1 - 10, completed_at=t1 - 5,
        ))
        store.create_task(TaskState(
            task_id="new_task", run_id="run_new", status="completed",
            parent_session_id="sess_001", project_id="proj_abc",
            started_at=t1 - 2, completed_at=t1,
        ))
        # Also create a running task — should not be returned
        store.create_task(TaskState(
            task_id="running_task", run_id="run_r", status="running",
            parent_session_id="sess_001", project_id="proj_abc",
            started_at=t1,
        ))

        last = store.get_last_completed_task("sess_001")
        assert last is not None
        assert last.task_id == "new_task"  # most recently completed


class TestSessionStoreDisabled:
    """When GA_CONTEXT_RUNTIME_ENABLED is not '1'."""

    def test_all_methods_return_none_or_empty(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)
        fd, path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        try:
            s = SessionStore(db_path=path)
            assert s.create_session("s1", "p1") is None
            assert s.get_session("s1") is None
            assert s.update_session(SessionRecord("s1", "p1", time.time())) is None
            assert s.create_task(TaskState("t1", "r1")) is None
            assert s.get_task("t1") is None
            assert s.update_task(TaskState("t1", "r1")) is None
            assert s.get_active_tasks() == []
            assert s.get_last_completed_task("s1") is None
            assert s.save_snapshot(SessionSnapshot(session_id="s1", project_id="p1")) is None
            assert s.get_snapshot("s1") is None
            assert s.build_recovery_payload("s1") is None
        finally:
            os.unlink(path)


class TestSessionSnapshots:
    """Runtime snapshot persistence for recovery and memory read-side."""

    def test_save_and_get_snapshot(self, store):
        snapshot = SessionSnapshot(
            session_id="sess_snapshot_001",
            project_id="proj_abc",
            current_mode="recovery",
            route_target="executor",
            execution_mode="multi_agent",
            pending_tool_call="run_tests",
            completed_steps=["route request", "write patch"],
            pending_steps=["run tests", "review diff"],
            modified_files=["core/openai_agentmain.py"],
            diff_refs=["diff_001"],
            diagnostic_refs=["diag_001"],
            review_status="needs_fix",
            collaboration_artifacts={"notes.md": {"version": 1}},
            event_log_position=42,
            last_user_intent="resume task",
            metadata={"source": "unit-test"},
        )
        saved = store.save_snapshot(snapshot)
        assert saved is not None

        got = store.get_snapshot("sess_snapshot_001")
        assert got is not None
        assert got.current_mode == "recovery"
        assert got.execution_mode == "multi_agent"
        assert got.pending_steps == ["run tests", "review diff"]
        assert got.collaboration_artifacts["notes.md"]["version"] == 1

    def test_build_recovery_payload(self, store):
        store.create_session("sess_recover_001", "proj_abc")
        store.create_task(TaskState(
            task_id="task_done",
            run_id="run_done",
            status="completed",
            summary="Implemented routing split",
            parent_session_id="sess_recover_001",
            project_id="proj_abc",
            started_at=time.time() - 10,
            completed_at=time.time(),
        ))
        store.save_snapshot(SessionSnapshot(
            session_id="sess_recover_001",
            project_id="proj_abc",
            current_mode="stopped",
            execution_mode="single_agent",
            pending_steps=["review changes"],
            last_user_intent="continue from last stop",
        ))

        payload = store.build_recovery_payload("sess_recover_001")
        assert payload is not None
        assert payload["session"]["session_id"] == "sess_recover_001"
        assert payload["snapshot"]["current_mode"] == "stopped"
        assert payload["last_task"]["summary"] == "Implemented routing split"
