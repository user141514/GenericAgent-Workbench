from __future__ import annotations

import json
import base64
import asyncio
import os
from pathlib import Path

import pytest

from core.protocol.agent import AgentBackend
from core.protocol.channel import AgentOutputChannel, QueueOutputChannel
from core.protocol.events import AgentOutputEvent
from core.protocol.input import AgentInput


class FakeAgentBackend(AgentBackend):
    def __init__(self):
        self.submitted: list[AgentInput] = []
        self.abort_count = 0
        self._running = False
        self.llm_no = 0
        self.history = []

    def submit(self, task: AgentInput) -> AgentOutputChannel:
        self.submitted.append(task)
        self._running = True
        channel = QueueOutputChannel()
        channel.put(AgentOutputEvent(kind="turn_start", turn=1, task_id=task.run_id or ""))
        channel.put(AgentOutputEvent(kind="chunk", text="hello", turn=1, task_id=task.run_id or ""))
        channel.put(AgentOutputEvent(kind="done", text="hello final", turn=1, task_id=task.run_id or ""))
        self._running = False
        return channel

    def abort(self) -> None:
        self.abort_count += 1
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def get_llm_name(self) -> str:
        return "fake-llm"

    def get_key_labels(self) -> list[str]:
        return ["fake"]

    def switch_to_key(self, index: int) -> str:
        self.llm_no = index
        return f"fake-{index}"

    def restore_history(self, restored, is_input_items=False):
        self.history = list(restored)


class FakeHttpResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _runtime(tmp_path: Path, agent: AgentBackend | None = None):
    from core.api.app import ReactApiRuntime

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "global_mem.txt").write_text("L2 facts", encoding="utf-8")
    (memory_dir / "global_mem_insight.txt").write_text("L1 insights", encoding="utf-8")
    (memory_dir / "history_memory_inbox.md").write_text("candidate inbox", encoding="utf-8")

    history_dir = tmp_path / "temp" / "model_responses"
    history_dir.mkdir(parents=True)
    (history_dir / "model_responses_20260101.txt").write_text(
        "=== USER ===\nhello history\n=== Response ===\nworld\n",
        encoding="utf-8",
    )

    return ReactApiRuntime(agent or FakeAgentBackend(), project_root=str(tmp_path))


def _sse_events(response_text: str) -> list[dict]:
    events = []
    for block in response_text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _collect_sse(async_iter) -> str:
    async def _collect():
        chunks = []
        async for item in async_iter:
            chunks.append(item)
        return "".join(chunks)

    return asyncio.run(_collect())


def test_create_run_and_stream_events(tmpdir):
    from core.api.app import RunCreateRequest

    tmp_path = Path(str(tmpdir))
    runtime = _runtime(tmp_path)
    created = runtime.create_run(RunCreateRequest(query="hello"))
    run_id = created.run_id

    events = _sse_events(_collect_sse(runtime.stream_events(run_id)))

    assert [event["kind"] for event in events] == ["turn_start", "chunk", "done"]
    assert events[-1]["text"] == "hello final"
    assert events[-1]["task_id"] == run_id


def test_research_run_streams_frontier_state_without_replacing_chunks(tmpdir):
    from core.api.app import RunCreateRequest

    tmp_path = Path(str(tmpdir))
    runtime = _runtime(tmp_path)
    created = runtime.create_run(
        RunCreateRequest(query="Turn failed benchmark evidence into a research strategy.")
    )

    events = _sse_events(_collect_sse(runtime.stream_events(created.run_id)))
    kinds = [event["kind"] for event in events]

    assert kinds[0] == "frontier_state"
    assert "chunk" in kinds
    assert kinds[-1] == "done"
    assert events[0]["metadata"]["frontier_state"]["enabled"] is True
    assert events[kinds.index("chunk")]["text"] == "hello"


def test_single_active_run_rejects_second_before_terminal(tmpdir):
    from fastapi import HTTPException
    from core.api.app import RunCreateRequest

    class BlockingFake(FakeAgentBackend):
        def submit(self, task: AgentInput) -> AgentOutputChannel:
            self.submitted.append(task)
            self._running = True
            return QueueOutputChannel()

    runtime = _runtime(Path(str(tmpdir)), agent=BlockingFake())
    runtime.create_run(RunCreateRequest(query="one"))
    with pytest.raises(HTTPException) as exc:
        runtime.create_run(RunCreateRequest(query="two"))
    assert exc.value.status_code == 409


def test_stop_run_calls_agent_abort(tmpdir):
    from core.api.app import RunCreateRequest

    agent = FakeAgentBackend()
    runtime = _runtime(Path(str(tmpdir)), agent=agent)
    run_id = runtime.create_run(RunCreateRequest(query="hello")).run_id

    stopped = runtime.stop_run(run_id)
    assert stopped.status == "stopping"
    assert agent.abort_count == 1


def test_upload_attachment_returns_metadata(tmpdir):
    from core.api.app import AttachmentUploadItem, AttachmentUploadRequest

    runtime = _runtime(Path(str(tmpdir)))
    payload = runtime.upload_attachments(
        AttachmentUploadRequest(
            files=[
                AttachmentUploadItem(
                    name="note.txt",
                    mime_type="text/plain",
                    data_base64=base64.b64encode(b"important note").decode("ascii"),
                )
            ]
        )
    )

    assert len(payload["attachments"]) == 1
    assert payload["attachments"][0]["name"] == "note.txt"
    assert payload["attachments"][0]["status"] == "ready"
    assert "distilled_text" in payload["attachments"][0]


def test_memory_endpoint_reads_project_memory(tmpdir):
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.memory()
    assert body["items"]["global_mem.txt"] == "L2 facts"
    assert body["items"]["global_mem_insight.txt"] == "L1 insights"
    assert body["items"]["history_memory_inbox.md"] == "candidate inbox"


def test_history_list_endpoint(tmpdir):
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.list_history()
    assert body["items"]
    assert body["items"][0]["filename"].startswith("model_responses_")


def test_create_app_registers_react_api_routes(tmpdir):
    from core.api.app import create_app

    app = create_app(agent=FakeAgentBackend(), project_root=str(tmpdir))
    paths = {route.path for route in app.routes}

    assert "/api/status" in paths
    assert "/api/runs" in paths
    assert "/api/runs/{run_id}/events" in paths
    assert "/api/runs/{run_id}/stop" in paths
    assert "/api/attachments" in paths
    assert "/api/history" in paths
    assert "/api/memory" in paths
    assert "/api/settings" in paths
    assert "/api/llm-config" in paths
    assert "/api/llm-config/check" in paths
    assert "/api/actions/new-chat" in paths
    assert "/api/actions/switch-key" in paths
    assert "/api/actions/reinject-tools" in paths
    assert "/api/autonomous/trigger" in paths


def test_llm_config_patch_masks_key_sets_env_and_reloads_agent(tmpdir, monkeypatch):
    from core.api import app as api_app
    from core.api.app import LlmConfigPatch

    tmp_path = Path(str(tmpdir))
    monkeypatch.setenv("GAGENT_DESKTOP_STATE_DIR", str(tmp_path / "state"))
    loaded_backends = []

    def fake_load_agent(backend):
        loaded_backends.append(backend)
        return FakeAgentBackend()

    monkeypatch.setattr(api_app, "load_agent", fake_load_agent)
    runtime = _runtime(tmp_path, agent=FakeAgentBackend())

    body = runtime.update_llm_config(
        LlmConfigPatch(
            provider="deepseek",
            api_key="sk-test-123456",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-v4-pro",
        )
    )

    assert body["configured"] is True
    assert body["api_key_masked"] == "sk-t...3456"
    assert "sk-test-123456" not in json.dumps(body)
    assert body["base_url"] == "https://api.deepseek.com/v1"
    assert body["model"] == "deepseek-v4-pro"
    assert body["backend"] == "fake-llm"
    assert loaded_backends == ["classic"]
    assert os.environ["GA_API_KEY"] == "sk-test-123456"
    assert os.environ["GA_API_BASE_URL"] == "https://api.deepseek.com/v1"


def test_llm_config_blank_key_preserves_existing_local_key(tmpdir, monkeypatch):
    from core.api import app as api_app
    from core.api.app import LlmConfigPatch

    tmp_path = Path(str(tmpdir))
    monkeypatch.setenv("GAGENT_DESKTOP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(api_app, "load_agent", lambda _backend: FakeAgentBackend())
    runtime = _runtime(tmp_path, agent=FakeAgentBackend())

    runtime.update_llm_config(
        LlmConfigPatch(api_key="sk-existing-abcdef", base_url="https://api.deepseek.com", model="deepseek-v4-pro")
    )
    body = runtime.update_llm_config(
        LlmConfigPatch(api_key="", base_url="http://127.0.0.1:8000", model="deepseek-v4-flash")
    )

    assert body["configured"] is True
    assert body["api_key_masked"] == "sk-e...cdef"
    assert os.environ["GA_API_KEY"] == "sk-existing-abcdef"
    assert os.environ["GA_API_BASE_URL"] == "http://127.0.0.1:8000"
    assert os.environ["GA_MODEL"] == "deepseek-v4-flash"


def test_llm_config_update_rejects_active_run(tmpdir, monkeypatch):
    from fastapi import HTTPException
    from core.api.app import LlmConfigPatch, RunCreateRequest

    class BlockingFake(FakeAgentBackend):
        def submit(self, task: AgentInput) -> AgentOutputChannel:
            self.submitted.append(task)
            self._running = True
            return QueueOutputChannel()

    tmp_path = Path(str(tmpdir))
    monkeypatch.setenv("GAGENT_DESKTOP_STATE_DIR", str(tmp_path / "state"))
    runtime = _runtime(tmp_path, agent=BlockingFake())
    runtime.create_run(RunCreateRequest(query="running"))

    with pytest.raises(HTTPException) as exc:
        runtime.update_llm_config(LlmConfigPatch(api_key="sk-new"))

    assert exc.value.status_code == 409


def test_llm_config_check_reads_models_and_probes_chat(tmpdir, monkeypatch):
    from core.api import llm_config
    from core.api.app import LlmConfigCheckRequest

    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return FakeHttpResponse(
            200,
            {
                "data": [
                    {"id": "deepseek-v4-pro"},
                    {"id": "deepseek-v4-flash"},
                ]
            },
        )

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        return FakeHttpResponse(200, {"choices": [{"message": {"content": "p"}}]})

    monkeypatch.setattr(llm_config.requests, "get", fake_get)
    monkeypatch.setattr(llm_config.requests, "post", fake_post)
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.check_llm_config(
        LlmConfigCheckRequest(
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-pro",
        )
    )

    assert body["ok"] is True
    assert body["base_url_normalized"] == "https://api.deepseek.com/v1"
    assert body["models"] == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert body["selected_model_valid"] is True
    assert body["chat_probe_ok"] is True
    assert calls[0][1] == "https://api.deepseek.com/v1/models"
    assert calls[1][1] == "https://api.deepseek.com/v1/chat/completions"
    assert calls[1][2]["json"]["model"] == "deepseek-v4-pro"


def test_llm_config_check_falls_back_to_chat_probe_when_models_endpoint_missing(tmpdir, monkeypatch):
    from core.api import llm_config
    from core.api.app import LlmConfigCheckRequest

    monkeypatch.setattr(llm_config.requests, "get", lambda *_args, **_kwargs: FakeHttpResponse(404, {}))
    monkeypatch.setattr(llm_config.requests, "post", lambda *_args, **_kwargs: FakeHttpResponse(200, {}))
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.check_llm_config(
        LlmConfigCheckRequest(
            api_key="sk-test",
            base_url="http://127.0.0.1:8000/v1",
            model="deepseek-v4-pro",
        )
    )

    assert body["ok"] is True
    assert body["models"] == ["deepseek-v4-pro", "deepseek-v4-flash"]
    assert body["selected_model_valid"] is True
    assert body["models_status_code"] == 404


def test_llm_config_check_reports_auth_failure(tmpdir, monkeypatch):
    from core.api import llm_config
    from core.api.app import LlmConfigCheckRequest

    monkeypatch.setattr(llm_config.requests, "get", lambda *_args, **_kwargs: FakeHttpResponse(401, {}))
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.check_llm_config(LlmConfigCheckRequest(api_key="bad-key"))

    assert body["ok"] is False
    assert body["stage"] == "auth"
    assert "rejected" in body["message"]


def test_llm_config_check_requires_key(tmpdir, monkeypatch):
    from core.api.app import LlmConfigCheckRequest

    monkeypatch.delenv("GA_API_KEY", raising=False)
    monkeypatch.setenv("GAGENT_DESKTOP_STATE_DIR", str(Path(str(tmpdir)) / "state"))
    runtime = _runtime(Path(str(tmpdir)))

    body = runtime.check_llm_config(LlmConfigCheckRequest(base_url="https://api.deepseek.com"))

    assert body["ok"] is False
    assert body["stage"] == "input"
    assert "API key" in body["message"]


def test_create_app_boots_unconfigured_when_keys_are_missing(tmpdir, monkeypatch):
    from core.api import app as api_app
    from core.api.app import RunCreateRequest, create_app

    def fail_load_agent(*_args, **_kwargs):
        raise RuntimeError("No API key configuration found")

    monkeypatch.setattr(api_app, "load_agent", fail_load_agent)

    app = create_app(project_root=str(tmpdir))
    runtime = app.state.runtime

    assert runtime.status()["backend"] == "unconfigured"
    created = runtime.create_run(RunCreateRequest(query="hello"))
    event = runtime.active_run.channel.get_nowait()
    assert event.kind == "error"
    assert event.metadata["configuration_required"] is True
    assert event.task_id == created.run_id


def test_create_app_does_not_hide_non_configuration_startup_errors(tmpdir, monkeypatch):
    from core.api import app as api_app
    from core.api.app import create_app

    def fail_load_agent(*_args, **_kwargs):
        raise RuntimeError("unexpected import failure")

    monkeypatch.setattr(api_app, "load_agent", fail_load_agent)

    with pytest.raises(RuntimeError, match="unexpected import failure"):
        create_app(project_root=str(tmpdir))


def test_settings_patch_updates_runtime_state(tmpdir):
    from core.api.app import SettingsPatch

    runtime = _runtime(Path(str(tmpdir)))
    updated = runtime.update_settings(
        SettingsPatch(
            routing_mode="classic",
            compact_assistant_history=False,
            autonomous_enabled=True,
        )
    )

    assert updated["routing_mode"] == "classic"
    assert updated["compact_assistant_history"] is False
    assert updated["autonomous_enabled"] is True


def test_switch_key_calls_agent_and_reports_index(tmpdir):
    from core.api.app import SwitchKeyRequest

    agent = FakeAgentBackend()
    runtime = _runtime(Path(str(tmpdir)), agent=agent)
    body = runtime.switch_key(SwitchKeyRequest(index=0))

    assert body["ok"] is True
    assert agent.llm_no == 0
    assert body["settings"]["current_key_index"] == 0


def test_reset_conversation_aborts_active_agent(tmpdir):
    agent = FakeAgentBackend()
    runtime = _runtime(Path(str(tmpdir)), agent=agent)

    body = runtime.reset_conversation()

    assert body["ok"] is True
    assert agent.abort_count == 1
    assert runtime.active_run is None


def test_autonomous_trigger_creates_auto_run(tmpdir):
    from core.api.app import AutonomousTriggerRequest

    agent = FakeAgentBackend()
    runtime = _runtime(Path(str(tmpdir)), agent=agent)

    created = runtime.trigger_autonomous(AutonomousTriggerRequest(mode="manual"))

    assert created.run_id.startswith("run_")
    assert agent.submitted
    assert agent.submitted[-1].query.startswith("[AUTO]")
    assert "自主行动" in agent.submitted[-1].query


def test_restore_history_returns_messages_and_updates_agent(tmpdir):
    agent = FakeAgentBackend()
    runtime = _runtime(Path(str(tmpdir)), agent=agent)

    body = runtime.restore_history("model_responses_20260101.txt")

    assert body["count"] == 1
    assert body["messages"] == [
        {"role": "user", "text": "hello history"},
        {"role": "assistant", "text": "world"},
    ]
    assert agent.history


def test_distill_delete_history_writes_inbox_and_removes_file(tmpdir):
    tmp_path = Path(str(tmpdir))
    runtime = _runtime(tmp_path)
    history_file = tmp_path / "temp" / "model_responses" / "model_responses_20260101.txt"

    body = runtime.distill_delete_history("model_responses_20260101.txt")

    assert body["ok"] is True
    assert body["deleted"] is True
    assert not history_file.exists()
    inbox = tmp_path / "memory" / "history_memory_inbox.md"
    assert "model_responses_20260101.txt" in inbox.read_text(encoding="utf-8")
