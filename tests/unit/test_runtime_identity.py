"""Phase 2c: RuntimeIdentity unit tests."""
import os
import time
from core.context.runtime_identity import detect_runtime, _get_session_id, RuntimeIdentity


class TestRuntimeIdentityEnabled:
    """Tests that require GA_CONTEXT_RUNTIME_ENABLED=1."""

    def setup_method(self):
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"

    def teardown_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_session_id_stable_within_process(self):
        """Same process produces same session_id."""
        rt1 = detect_runtime()
        rt2 = detect_runtime()
        assert rt1 is not None
        assert rt2 is not None
        assert rt1.session_id == rt2.session_id

    def test_session_id_format(self):
        """session_id starts with 'sess_'."""
        rt = detect_runtime()
        assert rt is not None
        assert rt.session_id.startswith("sess_")
        assert len(rt.session_id) == 17  # "sess_" + 12 hex chars

    def test_process_id_matches_os(self):
        """process_id matches os.getpid()."""
        rt = detect_runtime()
        assert rt is not None
        assert rt.process_id == os.getpid()

    def test_env_filter_only_ga_context(self):
        """Only GA_CONTEXT_* env vars are captured."""
        os.environ["GA_CONTEXT_RUNTIME_MODE"] = "preview"
        os.environ["GA_CONTEXT_PACKET_MAX_CHARS"] = "4000"
        os.environ["OTHER_VAR"] = "should_not_appear"
        try:
            rt = detect_runtime()
            assert rt is not None
            for key in rt.env_summary:
                assert key.startswith("GA_CONTEXT_"), f"Unexpected key: {key}"
            assert "OTHER_VAR" not in rt.env_summary
        finally:
            os.environ.pop("GA_CONTEXT_RUNTIME_MODE", None)
            os.environ.pop("GA_CONTEXT_PACKET_MAX_CHARS", None)
            os.environ.pop("OTHER_VAR", None)

    def test_env_values_truncated(self):
        """Env values are truncated to 80 chars."""
        long_value = "x" * 120
        os.environ["GA_CONTEXT_LONG_VAR"] = long_value
        try:
            rt = detect_runtime()
            assert rt is not None
            if "GA_CONTEXT_LONG_VAR" in rt.env_summary:
                assert len(rt.env_summary["GA_CONTEXT_LONG_VAR"]) <= 80
        finally:
            os.environ.pop("GA_CONTEXT_LONG_VAR", None)

    def test_agent_backend_from_param(self):
        """agent_backend comes from the parameter."""
        rt = detect_runtime(agent_backend="openai-agents")
        assert rt is not None
        assert rt.agent_backend == "openai-agents"

    def test_agent_backend_from_env(self):
        """agent_backend falls back to GA_AGENT_BACKEND env var."""
        os.environ["GA_AGENT_BACKEND"] = "openai-agents"
        try:
            rt = detect_runtime()  # no param
            assert rt is not None
            assert rt.agent_backend == "openai-agents"
        finally:
            os.environ.pop("GA_AGENT_BACKEND", None)

    def test_hostname_set(self):
        """hostname is a non-empty string."""
        rt = detect_runtime()
        assert rt is not None
        assert len(rt.hostname) > 0

    def test_started_at_is_recent(self):
        """started_at is close to now."""
        rt = detect_runtime()
        assert rt is not None
        assert abs(rt.started_at - time.time()) < 5.0

    def test_env_summary_empty_by_default(self):
        """When no non-ENABLED GA_CONTEXT_* vars are set, env_summary is minimal."""
        # Remove GA_CONTEXT_ vars except the ENABLED flag (which we need)
        saved = {}
        for key in list(os.environ.keys()):
            if key.startswith("GA_CONTEXT_") and key != "GA_CONTEXT_RUNTIME_ENABLED":
                saved[key] = os.environ.pop(key)
        try:
            rt = detect_runtime()
            assert rt is not None
            # Only GA_CONTEXT_RUNTIME_ENABLED should be present
            assert set(rt.env_summary.keys()) <= {"GA_CONTEXT_RUNTIME_ENABLED"}
        finally:
            os.environ.update(saved)


class TestRuntimeIdentityDisabled:
    """Tests when GA_CONTEXT_RUNTIME_ENABLED is not '1'."""

    def setup_method(self):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_detect_returns_none_when_disabled(self):
        rt = detect_runtime()
        assert rt is None
