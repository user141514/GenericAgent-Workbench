"""Tests for AgentBackend ABC and AgentInput."""

import pytest
from core.protocol.agent import AgentBackend
from core.protocol.input import AgentInput
from core.protocol.channel import AgentOutputChannel, QueueOutputChannel
from core.protocol.events import AgentOutputEvent


class TestAgentInput:
    """Tests for the AgentInput dataclass."""

    def test_minimal_construction(self):
        inp = AgentInput(query="hello")
        assert inp.query == "hello"
        assert inp.source == "user"
        assert inp.images is None
        assert inp.run_id is None

    def test_full_construction(self):
        inp = AgentInput(
            query="task",
            source="wechat",
            images=["/tmp/img.png"],
            run_id="run_001",
            session_id="sess_001",
        )
        assert inp.query == "task"
        assert inp.source == "wechat"
        assert inp.images == ["/tmp/img.png"]
        assert inp.run_id == "run_001"
        assert inp.session_id == "sess_001"

    def test_to_legacy_kwargs(self):
        inp = AgentInput(query="hello", source="user", images=["a.png"], run_id="r1")
        kwargs = inp.to_legacy_kwargs()
        assert kwargs["query"] == "hello"
        assert kwargs["source"] == "user"
        assert kwargs["images"] == ["a.png"]
        assert kwargs["run_id"] == "r1"

    def test_to_legacy_kwargs_images_none(self):
        inp = AgentInput(query="hello")
        kwargs = inp.to_legacy_kwargs()
        assert kwargs["images"] == []

    def test_metadata_defaults_empty(self):
        inp = AgentInput(query="x")
        assert inp.metadata == {}

    def test_metadata_custom(self):
        inp = AgentInput(query="x", metadata={"priority": 1})
        assert inp.metadata["priority"] == 1


class TestAgentBackendABC:
    """Verify AgentBackend ABC cannot be instantiated and defines the right interface."""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            AgentBackend()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all(self):
        class Partial(AgentBackend):
            def submit(self, task):
                return QueueOutputChannel()

        with pytest.raises(TypeError):
            Partial()  # type: ignore[abstract]

    def test_full_implementation_ok(self):
        class Full(AgentBackend):
            def submit(self, task):
                return QueueOutputChannel()

            def abort(self):
                pass

            @property
            def is_running(self):
                return False

            def get_llm_name(self):
                return "test"

            def get_key_labels(self):
                return ["key1"]

            def switch_to_key(self, index):
                return "key1"

        agent = Full()
        channel = agent.submit(AgentInput(query="test"))
        assert isinstance(channel, AgentOutputChannel)
        agent.abort()
        assert not agent.is_running
        assert agent.get_llm_name() == "test"
        assert agent.get_key_labels() == ["key1"]
        assert agent.switch_to_key(0) == "key1"


class TestAgentFactory:
    """Phase 5.5: load_agent() contract enforcement."""

    def test_classic_returns_agent_backend(self):
        """load_agent('classic') returns an isinstance(x, AgentBackend) object."""
        from core.agent_factory import load_agent
        from core.protocol.agent import AgentBackend

        agent = load_agent("classic")
        try:
            assert isinstance(agent, AgentBackend), (
                "classic backend must be an AgentBackend instance"
            )
        finally:
            agent.abort()

    def test_openai_now_returns_agent_backend(self):
        """Phase OA1: load_agent('openai') returns an AgentBackend (no longer blocked)."""
        from core.agent_factory import load_agent
        from core.protocol.agent import AgentBackend

        agent = load_agent("openai")
        try:
            assert isinstance(agent, AgentBackend), (
                "load_agent('openai') must return an AgentBackend after Phase OA1"
            )
        finally:
            agent.abort()

    def test_unknown_backend_raises_value_error(self):
        """load_agent('garbage') must raise ValueError."""
        from core.agent_factory import load_agent
        import pytest

        with pytest.raises(ValueError, match="Unknown backend"):
            load_agent("unknown_backend_xyz")

    def test_default_backend_is_classic(self):
        """load_agent() with no args defaults to classic."""
        from core.agent_factory import load_agent
        from core.protocol.agent import AgentBackend

        agent = load_agent()
        try:
            assert isinstance(agent, AgentBackend)
        finally:
            agent.abort()

    def test_classic_has_submit_returns_channel(self):
        """load_agent('classic').submit() returns AgentOutputChannel."""
        from core.agent_factory import load_agent
        from core.protocol.channel import AgentOutputChannel
        from core.protocol.input import AgentInput

        agent = load_agent("classic")
        try:
            channel = agent.submit(AgentInput(query="ping"))
            assert isinstance(channel, AgentOutputChannel)
        finally:
            agent.abort()


class TestLegacyQueueProperty:
    """Phase 5.5: QueueOutputChannel.legacy_queue public property."""

    def test_legacy_queue_is_accessible(self):
        """from_legacy_queue sets legacy_queue to the source raw queue."""
        import queue
        from core.protocol.channel import QueueOutputChannel

        raw_q = queue.Queue()
        raw_q.put({"done": "ok"})
        ch = QueueOutputChannel.from_legacy_queue(raw_q)

        import time
        time.sleep(0.3)
        # Public property returns the same raw queue object
        assert ch.legacy_queue is raw_q

    def test_legacy_queue_raises_without_from_legacy_queue(self):
        """Direct construction has no legacy_queue → raises RuntimeError."""
        import pytest
        from core.protocol.channel import QueueOutputChannel

        ch = QueueOutputChannel()
        with pytest.raises(RuntimeError, match="no legacy queue"):
            _ = ch.legacy_queue


class TestOpenAIOrchestratedAgentNative:
    """Phase OA1: OpenAIOrchestratedAgent now implements AgentBackend natively."""

    def test_isinstance_agent_backend(self):
        """Orchestrator must pass isinstance check."""
        from core.openai_agentmain import OpenAIOrchestratedAgent
        from core.protocol.agent import AgentBackend
        orch = OpenAIOrchestratedAgent()
        assert isinstance(orch, AgentBackend), (
            "OpenAIOrchestratedAgent must be an AgentBackend instance"
        )

    def test_is_running_is_property(self):
        """is_running must be a @property, not a plain attribute."""
        from core.openai_agentmain import OpenAIOrchestratedAgent
        orch = OpenAIOrchestratedAgent()
        assert isinstance(type(orch).is_running, property), (
            "is_running must be a @property"
        )
        assert orch.is_running is False

    def test_submit_returns_channel(self):
        """submit() must return AgentOutputChannel, not raw queue."""
        from core.openai_agentmain import OpenAIOrchestratedAgent
        from core.protocol.channel import AgentOutputChannel
        from core.protocol.input import AgentInput
        orch = OpenAIOrchestratedAgent()
        channel = orch.submit(AgentInput(query="test"))
        assert isinstance(channel, AgentOutputChannel)

    def test_put_task_still_works(self):
        """put_task() must still return raw queue.Queue for legacy callers."""
        from core.openai_agentmain import OpenAIOrchestratedAgent
        import queue
        orch = OpenAIOrchestratedAgent()
        raw_q = orch.put_task("test")
        assert isinstance(raw_q, queue.Queue)

    def test_abort_does_not_crash(self):
        """abort() must be callable without crashing."""
        from core.openai_agentmain import OpenAIOrchestratedAgent
        orch = OpenAIOrchestratedAgent()
        orch.abort()

    def test_load_agent_openai_now_works(self):
        """load_agent('openai') must return an AgentBackend (no longer blocked)."""
        from core.agent_factory import load_agent
        from core.protocol.agent import AgentBackend
        agent = load_agent("openai")
        try:
            assert isinstance(agent, AgentBackend)
        finally:
            agent.abort()

    def test_ensure_agent_backend_uses_isinstance(self):
        """ensure_agent_backend(orch) must pass through (no adapter)."""
        from core.agent_factory import ensure_agent_backend, load_agent
        orch = load_agent("openai")
        try:
            result = ensure_agent_backend(orch)
            assert result is orch, (
                "ensure_agent_backend should return the orch directly (isinstance path)"
            )
        finally:
            orch.abort()


class TestEnsureAgentBackend:
    """Phase 6c+: ensure_agent_backend() adapter for mixed agent types."""

    # ── case 1: AgentBackend passthrough ────────────────────────────────

    def test_agent_backend_passthrough(self):
        """GeneraticAgent(AgentBackend) is returned as-is."""
        from core.agent_factory import ensure_agent_backend, load_agent
        agent = load_agent("classic")
        try:
            result = ensure_agent_backend(agent)
            assert result is agent  # same object, no wrapping
        finally:
            agent.abort()

    # ── case 2: legacy adapter wraps put_task/abort/is_running ──────────

    def test_legacy_agent_adapted(self):
        """Object with put_task/abort/is_running gets submit() via adapter."""
        from core.agent_factory import ensure_agent_backend
        from core.protocol.agent import AgentBackend
        from core.protocol.input import AgentInput
        from core.protocol.channel import AgentOutputChannel

        class FakeLegacy:
            is_running = False

            def put_task(self, query, source="user", images=None, run_id=None):
                import queue
                q = queue.Queue()
                q.put({"done": "response", "source": source, "turn": 1})
                return q

            def abort(self):
                pass

            def get_llm_name(self):
                return "fake"

            def get_key_labels(self):
                return []

            def switch_to_key(self, n):
                return ""

        legacy = FakeLegacy()
        backend = ensure_agent_backend(legacy)
        assert isinstance(backend, AgentBackend)
        assert backend is not legacy  # wrapped

        channel = backend.submit(AgentInput(query="test"))
        assert isinstance(channel, AgentOutputChannel)

        import time
        time.sleep(0.3)
        from core.protocol.drain import AgentOutputDrainer
        d = AgentOutputDrainer(channel)
        d.collect(max_items=10)
        assert d.is_done
        assert d.full_text == "response"

    # ── case 3: submit() → AgentOutputChannel (not raw queue) ───────────

    def test_adapted_submit_returns_channel_not_raw_queue(self):
        """Legacy adapter's submit() returns AgentOutputChannel, not raw Queue."""
        from core.agent_factory import ensure_agent_backend
        from core.protocol.input import AgentInput
        from core.protocol.channel import AgentOutputChannel

        class FakeLegacy:
            is_running = False

            def put_task(self, query, source="user", images=None, run_id=None):
                import queue
                q = queue.Queue()
                q.put({"done": "ok", "source": source, "turn": 1})
                return q

            def abort(self):
                pass

        backend = ensure_agent_backend(FakeLegacy())
        channel = backend.submit(AgentInput(query="test"))
        assert isinstance(channel, AgentOutputChannel)
        assert not isinstance(channel, __import__("queue").Queue)

    # ── case 4: is_running property ─────────────────────────────────────

    def test_adapted_is_running_reflects_legacy_attribute(self):
        """Adapter's is_running property reads the legacy object's attribute."""
        from core.agent_factory import ensure_agent_backend

        class FakeLegacy:
            is_running = True

            def put_task(self, *a, **kw):
                import queue
                return queue.Queue()

            def abort(self):
                pass

        backend = ensure_agent_backend(FakeLegacy())
        assert backend.is_running is True

    # ── case 5: TypeError for incompatible object ───────────────────────

    def test_type_error_for_incompatible_object(self):
        """Object without put_task/abort → TypeError."""
        from core.agent_factory import ensure_agent_backend
        import pytest

        with pytest.raises(TypeError, match="Cannot adapt"):
            ensure_agent_backend(object())

    def test_type_error_for_object_with_only_put_task(self):
        """Object with put_task but no abort → TypeError."""
        from core.agent_factory import ensure_agent_backend
        import pytest

        class Incomplete:
            is_running = False

            def put_task(self, *a, **kw):
                import queue
                return queue.Queue()

        with pytest.raises(TypeError, match="Cannot adapt"):
            ensure_agent_backend(Incomplete())

    # ── backward compat: AgentBackend passthrough with explicit ABC ─────

    def test_explicit_agent_backend_subclass_passthrough(self):
        """Any AgentBackend subclass (e.g. mock) is returned as-is."""
        from core.agent_factory import ensure_agent_backend
        from core.protocol.agent import AgentBackend
        from core.protocol.input import AgentInput
        from core.protocol.channel import QueueOutputChannel

        class MyBackend(AgentBackend):
            def submit(self, task):
                return QueueOutputChannel()

            def abort(self):
                pass

            @property
            def is_running(self):
                return False

            def get_llm_name(self):
                return "my"

            def get_key_labels(self):
                return []

            def switch_to_key(self, i):
                return ""

        backend = MyBackend()
        result = ensure_agent_backend(backend)
        assert result is backend
