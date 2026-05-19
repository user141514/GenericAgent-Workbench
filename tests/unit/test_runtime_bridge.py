"""Regression tests: RuntimeEventMapper calls real RuntimeHost method signatures.

Verifies that protocol_bridge.py does not call non-existent methods like
``_emit`` with wrong parameters. Uses a mock that records calls and checks
they match the actual RuntimeHost API.
"""

import pytest


class MockRuntimeHost:
    """Records method calls for verification against real RuntimeHost API."""

    def __init__(self):
        self.calls = []
        self._session = _FakeSession()

    def start_session(self, *, user_intent, source):
        self.calls.append(("start_session", user_intent, source))

    def _require_session(self):
        return self._session

    def _append(self, event_type, *, payload):
        self.calls.append(("_append", event_type, payload))

    def request_tool(self, tool_name, *, target=None, risk_level="medium"):
        self.calls.append(("request_tool", tool_name, target, risk_level))

    def complete_tool(self, tool_name, *, result_summary="",
                      modified_files=None, diff_refs=None,
                      collaboration_artifacts=None):
        self.calls.append(("complete_tool", tool_name, result_summary))

    def fail_session(self, *, error):
        self.calls.append(("fail_session", error))

    def complete_session(self, *, summary=""):
        self.calls.append(("complete_session", summary))

    def request_stop(self, *, reason):
        self.calls.append(("request_stop", reason))

    def change_mode(self, to_mode, *, reason=""):
        self.calls.append(("change_mode", to_mode, reason))


class _FakeSession:
    turn_id = 0
    step_id = 0
    last_error = ""
    status = "running"
    review_status = None

    def advance_turn(self):
        self.turn_id += 1

    def advance_step(self):
        self.step_id += 1


class TestBridgeCallsRealMethods:
    """Every mapper method must call a real RuntimeHost method by correct name."""

    def test_on_turn_start_calls_append_not_emit(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_turn_start(turn=1, source="user", task_id="t1")

        assert len(host.calls) >= 1
        method_names = [c[0] for c in host.calls]
        assert "_append" in method_names, f"Should call _append, got {method_names}"
        assert "_emit" not in method_names, "Must NOT call non-existent _emit"

    def test_on_turn_end_calls_append_not_emit(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_turn_end(turn=1)

        method_names = [c[0] for c in host.calls]
        assert "_append" in method_names
        assert "_emit" not in method_names

    def test_on_tool_requested_calls_request_tool(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_tool_requested("file_read", {"path": "/tmp/x.txt"})

        tool_calls = [c for c in host.calls if c[0] == "request_tool"]
        assert len(tool_calls) == 1
        assert tool_calls[0][1] == "file_read"  # tool_name
        assert tool_calls[0][2] == "/tmp/x.txt"  # target extracted from args

    def test_on_tool_completed_calls_complete_tool(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_tool_completed("file_read", "read 500 bytes")

        tool_calls = [c for c in host.calls if c[0] == "complete_tool"]
        assert len(tool_calls) == 1
        assert tool_calls[0][1] == "file_read"

    def test_on_error_calls_fail_session(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_error("something broke")

        err_calls = [c for c in host.calls if c[0] == "fail_session"]
        assert len(err_calls) == 1
        assert err_calls[0][0] == "fail_session"

    def test_on_done_calls_complete_session(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_done("task finished")

        done_calls = [c for c in host.calls if c[0] == "complete_session"]
        assert len(done_calls) == 1

    def test_on_stop_requested_calls_request_stop_with_reason(self):
        from core.runtime.protocol_bridge import RuntimeEventMapper

        host = MockRuntimeHost()
        mapper = RuntimeEventMapper(host)
        mapper.on_stop_requested()

        stop_calls = [c for c in host.calls if c[0] == "request_stop"]
        assert len(stop_calls) == 1
        assert stop_calls[0][1] == "user_requested"

    def test_none_host_all_methods_noop(self):
        """All methods must accept host=None without crashing."""
        from core.runtime.protocol_bridge import RuntimeEventMapper

        mapper = RuntimeEventMapper(host=None)
        assert not mapper.active

        # Every public method must be callable with None host
        mapper.on_session_start("test")
        mapper.on_user_message("hello")
        mapper.on_turn_start(1)
        mapper.on_turn_end(1)
        mapper.on_tool_requested("read", {})
        mapper.on_tool_completed("read", "")
        mapper.on_error("err")
        mapper.on_done("done")
        mapper.on_stop_requested()
        # No exception = pass
