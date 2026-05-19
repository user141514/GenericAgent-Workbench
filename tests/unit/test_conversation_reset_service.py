"""Phase C1 tests for reset_agent_conversation_state()."""

import pytest


class FakeBackend:
    """Simulates an LLM backend with history and last_tools."""
    def __init__(self):
        self.history = [{"role": "user", "content": "old"}]
        self.last_tools = "cached_tools"


class FakeLLMClient:
    """Simulates agent.llmclient."""
    def __init__(self, backend=None):
        self.backend = backend


class FakeAgent:
    """Simulates a minimal agent for state cleanup testing."""
    def __init__(self, history=None, llmclient=None):
        self._history = history
        self.llmclient = llmclient
        self._aborted = False

    def abort(self):
        self._aborted = True

    @property
    def history(self):
        if self._history is None:
            raise AttributeError("no history")
        return self._history

    @history.setter
    def history(self, value):
        self._history = value


# ── tests ────────────────────────────────────────────────────────────────

class TestResetAgentConversationState:
    """Tests for reset_agent_conversation_state(agent)."""

    def test_calls_abort(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=[1, 2, 3])
        reset_agent_conversation_state(agent)
        assert agent._aborted

    def test_clears_history(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=[1, 2, 3])
        reset_agent_conversation_state(agent)
        assert agent.history == []

    def test_clears_backend_history(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        backend = FakeBackend()
        agent = FakeAgent(history=[1], llmclient=FakeLLMClient(backend=backend))
        reset_agent_conversation_state(agent)
        assert backend.history == []

    def test_clears_last_tools(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        backend = FakeBackend()
        llm = FakeLLMClient(backend=backend)
        llm.last_tools = "old_tools"
        agent = FakeAgent(history=[1], llmclient=llm)
        reset_agent_conversation_state(agent)
        assert agent.llmclient.last_tools == ""

    def test_no_history_does_not_crash(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=None)  # hasattr returns False for property
        # This should not raise
        reset_agent_conversation_state(agent)

    def test_no_llmclient_does_not_crash(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=[1], llmclient=None)
        reset_agent_conversation_state(agent)

    def test_llmclient_none_does_not_crash(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=[1], llmclient=FakeLLMClient(backend=None))
        reset_agent_conversation_state(agent)

    def test_backend_none_does_not_crash(self):
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        agent = FakeAgent(history=[1], llmclient=FakeLLMClient(backend=None))
        reset_agent_conversation_state(agent)

    def test_abort_exception_propagates(self):
        """Current stapp.py has no try/except around abort, so we don't swallow."""
        from frontends.services.conversation_reset_service import reset_agent_conversation_state

        class BrokenAgent:
            def abort(self):
                raise RuntimeError("abort failed")

        with pytest.raises(RuntimeError, match="abort failed"):
            reset_agent_conversation_state(BrokenAgent())

    def test_no_streamlit_dependency(self):
        """Service must not import streamlit."""
        import inspect
        from frontends.services.conversation_reset_service import reset_agent_conversation_state
        source = inspect.getsource(reset_agent_conversation_state)
        assert "streamlit" not in source
        assert "st." not in source
