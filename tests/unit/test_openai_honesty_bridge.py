from core.openai_runtime.honesty_bridge import (
    apply_openai_execution_honesty_gate,
    build_openai_execution_state,
)
from core.quality.execution_honesty import ExecutionAction


class FakeProfiler:
    def __init__(self):
        self.events = []

    def record_event(self, name, *, kind="", metadata=None):
        self.events.append({"name": name, "kind": kind, "metadata": metadata or {}})


def test_build_openai_execution_state_merges_executor_trace():
    state = build_openai_execution_state(
        execution_actions=[
            ExecutionAction(
                tool="planner",
                output_summary="ok",
                status="success",
            )
        ],
        executor_execution_state={
            "actual_actions": [
                {
                    "tool": "run_genericagent_executor",
                    "input_summary": "execute plan",
                    "output_summary": "metrics checked",
                    "status": "success",
                    "timestamp": "2026-06-13T10:00:00",
                }
            ],
            "state_delta": {
                "files_changed": ["report.md"],
                "checkpoints_updated": True,
                "metrics_verified": False,
            },
        },
    )

    assert [action.tool for action in state.actual_actions] == [
        "planner",
        "run_genericagent_executor",
    ]
    assert state.state_delta.files_changed == ("report.md",)
    assert state.state_delta.checkpoints_updated is True
    assert state.state_delta.metrics_verified is True
    assert state.response_claims == []


def test_build_openai_execution_state_preserves_explicit_executor_claims_only():
    state = build_openai_execution_state(
        execution_actions=[
            ExecutionAction(
                tool="run_genericagent_executor",
                output_summary="ok",
                status="success",
            )
        ],
        executor_execution_state={
            "response_claims": [
                {
                    "claim": "code_run produced metric 0.91",
                    "claim_type": "quant",
                    "evidence_status": "tool_verified",
                    "source": "classic_executor",
                    "evidence_type": "direct",
                    "confidence": 0.8,
                    "verified": True,
                }
            ]
        },
    )

    assert [claim.claim for claim in state.response_claims] == ["code_run produced metric 0.91"]


def test_successful_openai_tool_does_not_verify_arbitrary_numeric_or_causal_claim():
    text, blocked = apply_openai_execution_honesty_gate(
        "The benchmark is 42% better, therefore the project changed after the report.",
        execution_actions=[
            ExecutionAction(
                tool="run_genericagent_executor",
                output_summary="ok",
                status="success",
            )
        ],
        executor_execution_state={},
    )

    assert blocked is True
    assert "执行诚实检查" in text or "鎵ц璇氬疄妫€鏌" in text


def test_apply_openai_execution_honesty_gate_records_profiler_and_blocks():
    profiler = FakeProfiler()

    text, blocked = apply_openai_execution_honesty_gate(
        "已保存到文件。",
        execution_actions=[],
        executor_execution_state={},
        profiler=profiler,
    )

    assert blocked is True
    assert "执行诚实检查" in text
    assert profiler.events[0]["name"] == "execution_honesty_gate"
    assert profiler.events[0]["metadata"]["allowed"] is False
    assert "state_transition_claim_requires_trace" in profiler.events[0]["metadata"]["findings"]


def test_apply_openai_execution_honesty_gate_allows_with_file_delta():
    text, blocked = apply_openai_execution_honesty_gate(
        "已保存到文件。",
        execution_actions=[
            ExecutionAction(
                tool="run_genericagent_executor",
                output_summary="ok",
                status="success",
            )
        ],
        executor_execution_state={
            "state_delta": {"files_changed": ["notes.md"]},
        },
    )

    assert blocked is False
    assert text == "已保存到文件。"
