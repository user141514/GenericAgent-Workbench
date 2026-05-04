"""Phase 3b: TaskState dataclass unit tests."""
import time
from core.context.session_store import TaskState


class TestTaskStateLifecycle:
    """Test the TaskState dataclass invariants."""

    def test_default_status_is_pending(self):
        task = TaskState(task_id="t1", run_id="r1")
        assert task.status == "pending"

    def test_status_rejects_invalid(self):
        task = TaskState(task_id="t1", run_id="r1", status="invalid_status")
        assert task.status == "pending"  # falls back to default

    def test_valid_status_accepted(self):
        for status in ("pending", "running", "completed", "aborted", "error"):
            task = TaskState(task_id="t1", run_id="r1", status=status)
            assert task.status == status

    def test_summary_truncation(self):
        long_summary = "x" * 250
        task = TaskState(task_id="t1", run_id="r1", summary=long_summary)
        assert len(task.summary) == 200

    def test_short_summary_preserved(self):
        task = TaskState(task_id="t1", run_id="r1", summary="short")
        assert task.summary == "short"

    def test_timestamps_default_none(self):
        task = TaskState(task_id="t1", run_id="r1")
        assert task.started_at is None
        assert task.completed_at is None
        assert task.exit_reason is None

    def test_lifecycle_transitions(self):
        """pending → running → completed."""
        t1 = time.time()
        task = TaskState(task_id="t1", run_id="r1", status="pending")
        assert task.status == "pending"

        task.status = "running"
        task.started_at = t1
        assert task.status == "running"

        task.status = "completed"
        task.completed_at = t1 + 10
        task.exit_reason = "completed"
        task.turn_count = 5
        task.tool_count = 12
        assert task.status == "completed"
        assert task.turn_count == 5
        assert task.tool_count == 12

    def test_defaults_all_fields(self):
        task = TaskState(task_id="t1", run_id="r1")
        assert task.summary == ""
        assert task.source == "user"
        assert task.parent_session_id == ""
        assert task.project_id == ""
        assert task.turn_count == 0
        assert task.tool_count == 0
