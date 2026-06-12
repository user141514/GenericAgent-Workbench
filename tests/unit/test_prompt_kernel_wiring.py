from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_openai_agentmain_uses_shared_behavior_kernel():
    source = (PROJECT_ROOT / "core" / "openai_agentmain.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "build_agent_behavior_kernel" in source
    assert "_behavior_kernel()" in source


def test_classic_agentmain_uses_shared_behavior_kernel():
    source = (PROJECT_ROOT / "core" / "agentmain.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "build_agent_behavior_kernel" in source
    assert "prompt += build_agent_behavior_kernel()" in source
