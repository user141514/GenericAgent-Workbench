from __future__ import annotations

from types import SimpleNamespace

from core.agent_loop import BaseHandler, StepOutcome, agent_runner_loop
from core.llmcore import ToolClient


class _ToolBackend:
    name = "tool-backend"
    model = "tool-model"

    def __init__(self, response_text: str):
        self.response_text = response_text

    def ask(self, *_args, **_kwargs):
        yield self.response_text


class _RecordingHandler(BaseHandler):
    def __init__(self):
        self.parent = SimpleNamespace(_current_user_input="", active_profiler=None)
        self.dispatched: list[str] = []
        self.turn_end_calls: list[dict] = []
        self._done_hooks: list[str] = []

    def dispatch(self, tool_name, args, response, index=0):
        self.dispatched.append(tool_name)
        yield f"[tool {index}] {tool_name}\n"
        return StepOutcome(
            data=f"result-{tool_name}",
            next_prompt="continue",
            should_exit=False,
        )

    def turn_end_callback(self, response, tool_calls, tool_results, turn, next_prompt, exit_reason):
        self.turn_end_calls.append(
            {
                "turn": turn,
                "tool_calls": tool_calls,
                "tool_results": list(tool_results),
                "next_prompt": next_prompt,
                "exit_reason": exit_reason,
            }
        )
        return next_prompt


def _tool_use(name: str) -> str:
    return f'<tool_use>{{"name":"{name}","arguments":{{}}}}</tool_use>'


def _run_loop(*, verbose: bool, response_text: str, handler: _RecordingHandler | None = None):
    handler = handler or _RecordingHandler()
    client = ToolClient(_ToolBackend(response_text), auto_save_tokens=False)
    output = "".join(
        agent_runner_loop(
            client,
            system_prompt="system",
            user_input="user",
            handler=handler,
            tools_schema=[],
            max_turns=1,
            verbose=verbose,
        )
    )
    return output, handler


def test_verbose_loop_consumes_tool_calls_from_generator_return_value():
    output, handler = _run_loop(verbose=True, response_text=_tool_use("file_read"))

    assert "file_read" in handler.dispatched
    assert "[tool 0] file_read" in output


def test_compact_loop_consumes_tool_calls_from_generator_return_value():
    _output, handler = _run_loop(verbose=False, response_text=_tool_use("file_read"))

    assert handler.dispatched == ["file_read"]


def test_direct_answer_uses_untruncated_tool_results_for_decision(monkeypatch):
    import core.agent_loop as loop

    response_text = "".join(_tool_use(f"tool_{index}") for index in range(25))
    handler = _RecordingHandler()
    handler.parent._current_user_input = "read the exact answer"

    def fake_decision(*, tool_results, **_kwargs):
        joined = "\n".join(item["content"] for item in tool_results)
        return SimpleNamespace(
            should_answer="EARLY_KEY" in joined,
            answer="found early key" if "EARLY_KEY" in joined else "",
            reason="test",
            confidence=1.0,
            signals={"result_count": len(tool_results)},
        )

    def dispatch(tool_name, args, response, index=0):
        yield f"[tool {index}] {tool_name}\n"
        data = "EARLY_KEY" if index == 0 else f"result-{index}"
        return StepOutcome(data=data, next_prompt="continue", should_exit=False)

    handler.dispatch = dispatch
    monkeypatch.setenv("GENERIC_AGENT_DIRECT_ANSWER", "1")
    monkeypatch.setattr(loop, "try_direct_answer_from_tool_result", fake_decision)

    output, _handler = _run_loop(verbose=False, response_text=response_text, handler=handler)

    assert "found early key" in output
    assert handler.turn_end_calls[-1]["exit_reason"]["result"] == "DIRECT_ANSWER"
    assert len(handler.turn_end_calls[-1]["tool_results"]) == 10


def test_terminal_exit_reason_is_not_revived_by_done_hook():
    class TerminalHandler(_RecordingHandler):
        def dispatch(self, tool_name, args, response, index=0):
            self._done_hooks.append("should not run")
            yield "[terminal]\n"
            return StepOutcome(data="done", next_prompt=None, should_exit=False)

    _output, handler = _run_loop(
        verbose=False,
        response_text=_tool_use("finish"),
        handler=TerminalHandler(),
    )

    assert len(handler.turn_end_calls) == 1
    assert handler.turn_end_calls[0]["exit_reason"]["result"] == "CURRENT_TASK_DONE"
    assert handler.turn_end_calls[0]["next_prompt"] == ""
