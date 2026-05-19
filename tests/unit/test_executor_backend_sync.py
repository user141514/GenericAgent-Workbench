from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.openai_agentmain import OpenAIOrchestratedAgent


def _make_backend(class_name: str, *, api_base: str, model: str, name: str, api_key: str = "sk-test"):
    backend_cls = type(class_name, (), {})
    backend = backend_cls()
    backend.api_base = api_base
    backend.model = model
    backend.name = name
    backend.api_key = api_key
    backend.history = []
    return backend


class _FakeClient:
    def __init__(self, backend):
        self.backend = backend
        self.last_tools = ""


class _FakeClassicExecutor:
    def __init__(self, clients, current_idx: int = 0):
        self.llmclients = list(clients)
        self.llm_no = current_idx
        self.switch_calls: list[int] = []
        self.history = []
        self.handler = None
        self.stop_sig = False

    def switch_to_key(self, idx: int) -> str:
        self.llm_no = idx
        self.switch_calls.append(idx)
        return self.get_llm_name()

    def get_llm_name(self) -> str:
        backend = self.llmclients[self.llm_no].backend
        return f"{type(backend).__name__}/{backend.name}"


def _sample_variants():
    return [
        {
            "label": "claude-settings/anthropic",
            "backend_kind": "native_claude",
            "api_key": "sk-claude",
            "base_url": "https://api.deepseek.com/anthropic",
            "model": "deepseek-v4-pro[1m]",
            "source": "~/.claude/settings.json",
        },
        {
            "label": "key1_native_oai_config",
            "backend_kind": "native_oai",
            "api_key": "sk-key1",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "source": "mykey.py",
        },
        {
            "label": "key2_native_oai_config",
            "backend_kind": "native_oai",
            "api_key": "sk-key2",
            "base_url": "https://terminal.pub/v1",
            "model": "gpt-5.5",
            "source": "mykey.py",
        },
        {
            "label": "key3_native_oai_config",
            "backend_kind": "native_oai",
            "api_key": "sk-key3",
            "base_url": "https://terminal.pub/v1",
            "model": "claude-opus-4-6",
            "source": "mykey.py",
        },
    ]


def _sample_classic_executor(current_idx: int = 0) -> _FakeClassicExecutor:
    return _FakeClassicExecutor(
        [
            _FakeClient(
                _make_backend(
                    "NativeOAISession",
                    api_base="https://api.deepseek.com/v1",
                    model="deepseek-v4-pro",
                    name="deepseek-v4-pro",
                    api_key="sk-key1",
                )
            ),
            _FakeClient(
                _make_backend(
                    "NativeOAISession",
                    api_base="https://terminal.pub/v1",
                    model="gpt-5.5",
                    name="GPT5.5",
                    api_key="sk-key2",
                )
            ),
            _FakeClient(
                _make_backend(
                    "NativeOAISession",
                    api_base="https://terminal.pub/v1",
                    model="claude-opus-4-6",
                    name="claude-opus-4-6",
                    api_key="sk-key3",
                )
            ),
        ],
        current_idx=current_idx,
    )


def _build_orchestrator(classic_idx: int = 0) -> OpenAIOrchestratedAgent:
    orch = OpenAIOrchestratedAgent.__new__(OpenAIOrchestratedAgent)
    orch.variants = _sample_variants()
    orch.supports_llm_switch = True
    orch.llm_no = 0
    orch.model_name = orch.variants[0]["model"]
    orch._variant_label = orch.variants[0]["label"]
    orch._variant_backend_kind = orch.variants[0]["backend_kind"]
    orch._classic_executor = _sample_classic_executor(current_idx=classic_idx)
    orch._cached_agent_graph = None
    orch._cached_agent_graph_model_id = None
    orch._active_sdk_model = None
    orch.active_profiler = None
    orch._active_span_id = None
    orch._profile_run_id = None
    orch._executor_result_state = None
    orch.verbose = False
    return orch


def test_resolve_classic_executor_index_matches_backend_not_raw_variant_index():
    orch = _build_orchestrator()

    assert orch._resolve_classic_executor_index(0) == 0
    assert orch._resolve_classic_executor_index(2) == 1
    assert orch._resolve_classic_executor_index(3) == 2


def test_sync_from_classic_key_index_maps_into_orchestrator_variant_space():
    orch = _build_orchestrator()

    orch.sync_from_classic_key_index(0)
    assert orch.llm_no == 1
    assert orch._classic_executor.llm_no == 0

    orch.sync_from_classic_key_index(2)
    assert orch.llm_no == 3
    assert orch._classic_executor.llm_no == 2


def test_run_classic_executor_task_retries_on_backend_channel_failure():
    orch = _build_orchestrator(classic_idx=1)
    orch.llm_no = 2
    orch.model_name = orch.variants[2]["model"]
    orch._variant_label = orch.variants[2]["label"]
    orch._variant_backend_kind = orch.variants[2]["backend_kind"]
    orch._run_classic_executor_task_once = MagicMock(
        side_effect=[
            "Error: HTTP 503 ... No available channel for model gpt-5.5",
            "OK",
        ]
    )

    allowed = SimpleNamespace(
        allowed=True,
        mode="allow",
        risk_level="low",
        matched_patterns=[],
        reason="",
    )
    with patch("core.runtime.execution_policy.get_policy_mode", return_value="allow"), patch(
        "core.runtime.execution_policy.evaluate_operation",
        return_value=allowed,
    ):
        result = orch._run_classic_executor_task("reply with ok", "reply with ok")

    assert result == "OK"
    assert orch._run_classic_executor_task_once.call_count == 2
    assert orch._classic_executor.switch_calls == [0]
