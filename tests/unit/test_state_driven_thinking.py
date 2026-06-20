from core.quality.state_driven_thinking import (
    STATE_DRIVEN_ACTIONS,
    build_state_driven_thinking_context,
    should_inject_state_driven_thinking,
    state_driven_thinking_enabled,
)


def test_state_driven_thinking_enabled_by_default(monkeypatch):
    monkeypatch.delenv("GENERIC_AGENT_STATE_DRIVEN_THINKING", raising=False)

    assert state_driven_thinking_enabled() is True


def test_should_inject_for_complex_implementation_request():
    assert should_inject_state_driven_thinking("帮我修复这个历史恢复 bug，并同步 npm 包")


def test_should_not_inject_for_simple_read_request():
    assert not should_inject_state_driven_thinking("读取 README 第一行")


def test_context_contains_control_contract_without_visible_json_requirement():
    context = build_state_driven_thinking_context("审计这份手稿，找出关键反例")

    assert context["matched"] is True
    assert context["chars"] == len(context["block"])
    block = context["block"]
    assert "### State-Driven Thinking Core" in block
    assert "状态不是日志" in block
    assert "DECOMPOSE" in block
    assert "VERIFY" in block
    assert "COUNTER" in block
    assert "STOP" in block
    assert "fatal / major / minor" in block
    assert "Do not expose the full JSON state" in block
    assert "继续深入" in block


def test_action_vocabulary_is_fixed_and_complete():
    assert STATE_DRIVEN_ACTIONS == (
        "DECOMPOSE",
        "EXPAND",
        "VERIFY",
        "COUNTER",
        "REWEIGHT",
        "NARROW",
        "SYNTHESIZE",
        "REWRITE",
        "STOP",
    )


def test_quality_package_exports_state_driven_context():
    from core import quality

    assert quality.build_state_driven_thinking_context("修复 bug")["matched"] is True


def test_runtime_entrypoints_reference_state_driven_context():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    agentmain = (root / "core" / "agentmain.py").read_text(encoding="utf-8")
    openai_agentmain = (root / "core" / "openai_agentmain.py").read_text(encoding="utf-8")

    assert "build_state_driven_thinking_context" in agentmain
    assert "build_state_driven_thinking_context" in openai_agentmain
    assert "should_inject_state_driven_thinking" in openai_agentmain
