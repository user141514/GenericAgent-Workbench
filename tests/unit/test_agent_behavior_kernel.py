from __future__ import annotations


def test_agent_behavior_kernel_is_compact_and_auditable(monkeypatch):
    monkeypatch.delenv("GENERIC_AGENT_PROMPT_KERNEL", raising=False)
    monkeypatch.delenv("GENERIC_AGENT_PROMPT_KERNEL_MAX_CHARS", raising=False)

    from core.prompts.agent_behavior_kernel import build_agent_behavior_kernel

    block = build_agent_behavior_kernel()
    assert block
    assert len(block) <= 1600

    required_phrases = [
        "calm, warm, plainspoken",
        "avoid performative certainty",
        "Evidence first",
        "Execution honesty",
        "Current information",
        "Memory discipline",
        "smallest useful action",
        "facts, assumptions",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in block]
    assert missing == []


def test_agent_behavior_kernel_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GENERIC_AGENT_PROMPT_KERNEL", "0")

    from core.prompts.agent_behavior_kernel import (
        agent_behavior_kernel_enabled,
        build_agent_behavior_kernel,
    )

    assert agent_behavior_kernel_enabled() is False
    assert build_agent_behavior_kernel() == ""


def test_agent_behavior_kernel_honors_char_budget(monkeypatch):
    monkeypatch.delenv("GENERIC_AGENT_PROMPT_KERNEL", raising=False)
    monkeypatch.setenv("GENERIC_AGENT_PROMPT_KERNEL_MAX_CHARS", "240")

    from core.prompts.agent_behavior_kernel import build_agent_behavior_kernel

    block = build_agent_behavior_kernel()
    assert 0 < len(block) <= 240
