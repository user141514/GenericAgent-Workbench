"""Shared pytest fixtures for GenericAgent Workbench tests."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ── Global mock: prevent agents SDK import cascade ─────────────────
# Injected once at test collection time so all test files share the same mock.
# The `agent_graph` fixture below patches _build_model to use a mock model,
# which is the only other thing needed to call _build_agent_graph() safely.


class _FakeAgent:
    """Captures Agent() constructor kwargs for inspection in tests."""

    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "unknown")
        self.handoff_description = kwargs.get("handoff_description", "")
        self.instructions = kwargs.get("instructions", "")
        self.tools = kwargs.get("tools", []) or []
        self.handoffs = kwargs.get("handoffs", []) or []
        self.model = kwargs.get("model")
        self._all_kwargs = kwargs

    def __repr__(self):
        return f"_FakeAgent(name={self.name!r})"


def _make_fake_tool(fn, **kw):
    """Wrap a function as a fake tool, preserving name and metadata."""
    wrapper = MagicMock()
    name_override = kw.get("name_override")
    wrapper.name = name_override or getattr(fn, "__name__", "unknown_tool")
    wrapper.__wrapped__ = fn
    wrapper._tool_kwargs = kw
    return wrapper


def _setup_agents_mock():
    """Set up mock agents module in sys.modules (idempotent)."""
    if "agents" in sys.modules and not isinstance(sys.modules["agents"], MagicMock):
        return  # real module already loaded, skip
    mock_agents = MagicMock()
    mock_agents.Agent = MagicMock(side_effect=lambda **kw: _FakeAgent(**kw))
    mock_agents.function_tool = MagicMock(
        side_effect=lambda **kw: lambda fn: _make_fake_tool(fn, **kw)
    )
    mock_agents.Runner = MagicMock()
    mock_agents.set_tracing_disabled = MagicMock()
    mock_agents.Model = MagicMock()
    mock_agents.items = MagicMock()
    mock_agents.models = MagicMock()
    mock_agents.stream_events = MagicMock()
    mock_agents.usage = MagicMock()
    sys.modules["agents"] = mock_agents
    for sub in [
        "agents.items", "agents.models",
        "agents.models.chatcmpl_converter", "agents.models.fake_id",
        "agents.stream_events", "agents.usage",
    ]:
        if sub not in sys.modules:
            sys.modules[sub] = MagicMock()


_setup_agents_mock()


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def project_root() -> str:
    """Return the absolute path to the project root directory."""
    return PROJECT_ROOT


@pytest.fixture
def mock_mykeys() -> dict:
    """Return a valid mykeys config dict for testing without real API keys."""
    return {
        "native_oai_config": {
            "name": "test-backend",
            "apikey": "test-key-12345",
            "apibase": "https://api.test.example.com",
            "model": "test-model",
            "stream": False,
            "max_retries": 1,
            "connect_timeout": 5,
            "read_timeout": 10,
        }
    }


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temporary workspace with basic file structure for testing."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test_file.txt").write_text("line 1\nline 2\nline 3\n")
    return workspace


@pytest.fixture
def agent_graph():
    """Build the real agent graph with a mocked model (available to all tests)."""
    from unittest.mock import patch
    from core.openai_agentmain import OpenAIOrchestratedAgent

    mock_model = MagicMock()
    orchestrator = OpenAIOrchestratedAgent.__new__(OpenAIOrchestratedAgent)
    orchestrator._active_sdk_model = mock_model
    orchestrator.input_items = []
    orchestrator.history = []
    orchestrator.llm_no = 0
    orchestrator._cached_agent_graph = None
    orchestrator._cached_agent_graph_model_id = None
    orchestrator._run_store = None
    orchestrator._run_classic_executor_task = MagicMock()
    orchestrator._store_executor_result_state = MagicMock()

    with patch.object(OpenAIOrchestratedAgent, "_build_model", return_value=mock_model):
        return orchestrator._build_agent_graph("test request", executor_progress=None)

