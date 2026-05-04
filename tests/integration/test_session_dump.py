"""
Integration tests for P4: session dump/restore.

Verifies:
1. dump_session() writes a JSON file
2. restore_session() reads it back
3. Sensitive content is truncated
4. 7-day auto-cleanup
5. cleanup_expired_dumps() removes old files
6. list_session_dumps() returns available dumps
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.context.session_dump import (
    cleanup_expired_dumps,
    dump_session,
    list_session_dumps,
    restore_session,
)


# ══════════════════════════════════════════════════════════════════════
# Dump tests
# ══════════════════════════════════════════════════════════════════════

class TestSessionDump:
    def test_dump_creates_file(self, tmp_path):
        path = dump_session(
            session_id="test_session_1",
            active_task="Fixing memory bug",
            project_root=tmp_path,
        )
        assert path is not None
        assert os.path.exists(path)
        assert path.endswith(".json")

    def test_dump_includes_active_task(self, tmp_path):
        dump_session(
            session_id="s1",
            active_task="Implement feature X",
            key_info="user prefers dark mode",
            project_root=tmp_path,
        )
        data = restore_session("s1", project_root=tmp_path)
        assert data is not None
        assert data["active_task"] == "Implement feature X"
        assert "dark mode" in data["key_info"]

    def test_dump_includes_pending_changes(self, tmp_path):
        dump_session(
            session_id="s2",
            active_task="Refactor",
            pending_changes=["config.yaml: port 8080→3000", "nginx.conf: proxy_pass updated"],
            project_root=tmp_path,
        )
        data = restore_session("s2", project_root=tmp_path)
        assert data is not None
        assert len(data["pending_changes"]) == 2

    def test_dump_includes_tool_events(self, tmp_path):
        dump_session(
            session_id="s3",
            active_task="Debug",
            tool_events=[
                {"name": "file_read", "status": "done", "summary": "Read config.yaml"},
                {"name": "code_run", "status": "done", "summary": "Ran tests"},
            ],
            project_root=tmp_path,
        )
        data = restore_session("s3", project_root=tmp_path)
        assert data is not None
        assert len(data["tool_events"]) == 2
        assert data["tool_events"][0]["name"] == "file_read"


# ══════════════════════════════════════════════════════════════════════
# Restore tests
# ══════════════════════════════════════════════════════════════════════

class TestSessionRestore:
    def test_restore_returns_none_for_missing(self, tmp_path):
        result = restore_session("nonexistent", project_root=tmp_path)
        assert result is None

    def test_restore_returns_data(self, tmp_path):
        dump_session(
            session_id="r1",
            active_task="Restore test",
            history_summary="User asked about memory leak",
            project_root=tmp_path,
        )
        data = restore_session("r1", project_root=tmp_path)
        assert data is not None
        assert data["session_id"] == "r1"
        assert "memory leak" in data["history_summary"]

    def test_restore_truncated_fields(self, tmp_path):
        """Verify long content is truncated, not stored in full."""
        dump_session(
            session_id="r2",
            active_task="T",
            key_info="x" * 3000,  # exceeds _MAX_KEY_INFO_CHARS (1000)
            history_summary="y" * 5000,  # exceeds _MAX_HISTORY_SUMMARY_CHARS (2000)
            project_root=tmp_path,
        )
        data = restore_session("r2", project_root=tmp_path)
        assert data is not None
        # Key info and history should be truncated
        assert len(data["key_info"]) <= 1100  # small margin
        assert len(data["history_summary"]) <= 2100


# ══════════════════════════════════════════════════════════════════════
# Cleanup tests
# ══════════════════════════════════════════════════════════════════════

class TestSessionCleanup:
    def test_cleanup_removes_old_dumps(self, tmp_path):
        dump_dir = tmp_path / "temp" / "session_dumps"
        dump_dir.mkdir(parents=True)

        # Create an old dump (8 days ago)
        old_file = dump_dir / "old_session.json"
        old_data = {"session_id": "old", "dumped_at": "2020-01-01T00:00:00"}
        old_file.write_text(json.dumps(old_data), encoding="utf-8")
        # Set mtime to 8 days ago
        old_time = time.time() - (8 * 86400)
        os.utime(str(old_file), (old_time, old_time))

        # Create a recent dump
        new_file = dump_dir / "new_session.json"
        new_data = {
            "session_id": "new",
            "dumped_at": "2026-05-04T00:00:00",
        }
        new_file.write_text(json.dumps(new_data), encoding="utf-8")

        removed = cleanup_expired_dumps(project_root=tmp_path)
        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_restore_auto_cleans_expired(self, tmp_path):
        dump_dir = tmp_path / "temp" / "session_dumps"
        dump_dir.mkdir(parents=True)

        old_file = dump_dir / "expired.json"
        old_data = {"session_id": "expired", "dumped_at": "2020-01-01T00:00:00"}
        old_file.write_text(json.dumps(old_data), encoding="utf-8")

        result = restore_session("expired", project_root=tmp_path)
        assert result is None  # should be auto-cleaned
        assert not old_file.exists()


# ══════════════════════════════════════════════════════════════════════
# List tests
# ══════════════════════════════════════════════════════════════════════

class TestSessionList:
    def test_list_returns_dumps(self, tmp_path):
        dump_session(session_id="l1", active_task="Task 1", project_root=tmp_path)
        dump_session(session_id="l2", active_task="Task 2", project_root=tmp_path)

        dumps = list_session_dumps(project_root=tmp_path)
        assert len(dumps) == 2
        tasks = {d["active_task"] for d in dumps}
        assert "Task 1" in tasks
        assert "Task 2" in tasks

    def test_list_empty_dir(self, tmp_path):
        dumps = list_session_dumps(project_root=tmp_path)
        assert dumps == []
