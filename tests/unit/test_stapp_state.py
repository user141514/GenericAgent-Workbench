"""Phase F1 tests for ensure_stapp_session_state()."""

import pytest


# ── minimal dict-like state for testing ──────────────────────────────────

class FakeState(dict):
    """Simulates st.session_state for testing."""
    pass


# ── tests ────────────────────────────────────────────────────────────────

class TestEnsureStappSessionState:
    """ensure_stapp_session_state() behaviour."""

    def test_missing_keys_initialised(self):
        from frontends.stapp_state import ensure_stapp_session_state
        state = FakeState()
        ensure_stapp_session_state(state)
        assert state["autonomous_enabled"] is False
        assert state["agent_running"] is False
        assert state["routing_mode"] == "auto"
        assert state["content_event"] == 0

    def test_existing_keys_not_overwritten(self):
        from frontends.stapp_state import ensure_stapp_session_state
        state = FakeState()
        state["routing_mode"] = "multi_agent"
        state["content_event"] = 5
        ensure_stapp_session_state(state)
        assert state["routing_mode"] == "multi_agent"
        assert state["content_event"] == 5

    def test_all_required_keys_present(self):
        from frontends.stapp_state import _DEFAULTS
        required = {
            "autonomous_enabled", "show_history", "show_memory",
            "show_watchtower", "compact_assistant_history",
            "uploaded_files", "processed_upload_cache", "upload_widget_nonce",
            "agent_running", "_stream_dq", "content_event",
            "routing_mode", "pending_routing", "partial_response",
            "current_turn", "stream_started", "stop_requested",
            "stop_requested_at", "orchestrator", "last_submitted_input",
            "messages", "msg_counter",
        }
        assert set(_DEFAULTS.keys()) == required

    def test_list_defaults_not_shared(self):
        """Each call creates fresh list/dict instances (no shared mutable state)."""
        from frontends.stapp_state import ensure_stapp_session_state
        s1 = FakeState()
        s2 = FakeState()
        ensure_stapp_session_state(s1)
        ensure_stapp_session_state(s2)
        s1["uploaded_files"].append({"name": "test.txt"})
        assert s2["uploaded_files"] == []

    def test_dict_defaults_not_shared(self):
        from frontends.stapp_state import ensure_stapp_session_state
        s1 = FakeState()
        s2 = FakeState()
        ensure_stapp_session_state(s1)
        ensure_stapp_session_state(s2)
        s1["processed_upload_cache"]["k"] = "v"
        assert s2["processed_upload_cache"] == {}

    def test_no_streamlit_dependency(self):
        """Function must not import streamlit."""
        import inspect
        from frontends.stapp_state import ensure_stapp_session_state
        source = inspect.getsource(ensure_stapp_session_state)
        assert "streamlit" not in source
        assert "import st" not in source

    def test_no_agent_dependency(self):
        """Function must not call agent methods."""
        import inspect
        from frontends.stapp_state import ensure_stapp_session_state
        source = inspect.getsource(ensure_stapp_session_state)
        assert "agent.abort" not in source
        assert "agent.submit" not in source
