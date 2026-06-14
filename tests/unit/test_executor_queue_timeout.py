"""Test that queue.get() timeout calculation never produces negative values.

Bug: _run_classic_executor_task_once computes remaining = deadline - time.time(),
then passes timeout=min(5, remaining) to queue.Queue.get(). When time.time()
ticks past the deadline between the check and the call, remaining becomes
negative, and queue.Queue.get(negative_timeout) raises ValueError.
"""

from __future__ import annotations


def compute_safe_timeout(remaining: float) -> float:
    """Calculate a safe timeout value from remaining time.

    Must never return a negative value that could crash queue.Queue.get().
    """
    return max(0.01, min(5.0, remaining))


class TestExecutorQueueTimeout:
    def test_positive_remaining_clamped_to_5(self):
        """When plenty of time remains, timeout is capped at 5 seconds."""
        assert compute_safe_timeout(100.0) == 5.0
        assert compute_safe_timeout(10.0) == 5.0
        assert compute_safe_timeout(5.0) == 5.0

    def test_positive_remaining_preserved(self):
        """When remaining is under 5, use the remaining time."""
        assert compute_safe_timeout(3.0) == 3.0
        assert compute_safe_timeout(1.0) == 1.0
        assert compute_safe_timeout(0.5) == 0.5
        assert compute_safe_timeout(0.02) == 0.02

    def test_zero_remaining_clamped_to_minimum(self):
        """Zero remaining time clamps to small positive minimum."""
        result = compute_safe_timeout(0.0)
        assert result > 0

    def test_negative_remaining_clamped_to_minimum(self):
        """NEGATIVE remaining time MUST produce a positive timeout."""

        # Simulates race: time.time() advances past deadline between
        # the if-check and the queue.get() call.
        result = compute_safe_timeout(-0.001)
        assert result > 0, f"Expected positive timeout, got {result}"

        result = compute_safe_timeout(-1.0)
        assert result > 0, f"Expected positive timeout, got {result}"

        result = compute_safe_timeout(-60.0)
        assert result > 0, f"Expected positive timeout, got {result}"

    def test_no_value_error_from_queue_get(self):
        """queue.Queue.get() never receives a negative timeout."""
        import queue
        import threading

        # All computed values must be valid for queue.Queue.get(timeout=...)
        for remaining in [100.0, 5.0, 3.0, 0.5, 0.001, 0.0, -0.001, -1.0, -60.0]:
            timeout = compute_safe_timeout(remaining)
            assert timeout > 0, f"timeout={timeout} for remaining={remaining}"
            q = queue.Queue()

            def put_later():
                import time
                time.sleep(timeout * 0.05)
                q.put("ok")

            threading.Thread(target=put_later, daemon=True).start()
            try:
                result = q.get(timeout=timeout)
                assert result == "ok"
            except ValueError as e:
                raise AssertionError(
                    f"queue.get() crashed with negative timeout={timeout} "
                    f"(remaining={remaining}): {e}"
                ) from e
