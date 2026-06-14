"""Test that create_run is concurrency-safe.

Bug: Two simultaneous POST /api/runs requests can both pass the
``active_run.terminal`` check and create overlapping runs.
Fix: Add a threading.Lock around the check-and-set.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from core.api.app import ActiveRun, ReactApiRuntime, RunCreateRequest
from core.protocol.channel import QueueOutputChannel


class _FakeAgent:
    """Agent stub that returns a valid output channel for every submit()."""

    def submit(self, task):
        ch = QueueOutputChannel()
        ch.close()
        return ch

    def abort(self):
        pass

    @property
    def is_running(self):
        return False

    def get_llm_name(self):
        return "test"

    def get_key_labels(self):
        return []

    def switch_to_key(self, index):
        return "test"


def _make_runtime():
    """Create a ReactApiRuntime with a fake agent."""
    agent = _FakeAgent()
    return ReactApiRuntime(agent, project_root="/tmp/test")


class TestCreateRunConcurrency:
    def test_sequential_runs_work(self):
        """Normal case: two sequential runs should both succeed."""
        rt = _make_runtime()

        r1 = rt.create_run(RunCreateRequest(query="hello"))
        assert r1.run_id

        # First run must be terminal before second can start
        rt.active_run.terminal = True
        r2 = rt.create_run(RunCreateRequest(query="world"))
        assert r2.run_id
        assert r1.run_id != r2.run_id

    def test_second_run_rejected_when_first_active(self):
        """A second create_run raises 409 when a run is active."""
        rt = _make_runtime()
        rt.create_run(RunCreateRequest(query="first"))

        with pytest.raises(HTTPException) as exc_info:
            rt.create_run(RunCreateRequest(query="second"))
        assert exc_info.value.status_code == 409

    def test_concurrent_create_run_only_one_succeeds(self):
        """Two concurrent create_run calls: exactly one succeeds, one gets 409."""

        rt = _make_runtime()
        results = {"success": 0, "error": 0}
        barrier = threading.Barrier(2, timeout=5)

        def try_create(query):
            barrier.wait()  # both threads release simultaneously
            try:
                rt.create_run(RunCreateRequest(query=query))
                results["success"] += 1
            except HTTPException:
                results["error"] += 1

        t1 = threading.Thread(target=try_create, args=("alpha",))
        t2 = threading.Thread(target=try_create, args=("beta",))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not t1.is_alive(), "Thread 1 hung"
        assert not t2.is_alive(), "Thread 2 hung"
        assert results["success"] == 1, (
            f"Expected exactly 1 success, got {results['success']}"
        )
        assert results["error"] == 1, (
            f"Expected exactly 1 error, got {results['error']}"
        )
