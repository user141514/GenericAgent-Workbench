from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_openai_runtime_wires_research_workflow_gate():
    source = (PROJECT_ROOT / "core" / "openai_agentmain.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    required = [
        "build_research_workflow_context",
        "research_workflow_enabled",
        "should_inject_research_workflow",
        "research_workflow_context_injected",
        "research_workflow_context_chars",
        "research_workflow_required_sections",
        "research_workflow_required_audit_gates",
        "research_workflow_gate",
        "research_workflow=research_workflow_block",
    ]
    missing = [item for item in required if item not in source]
    assert missing == []


def test_context_adapter_accepts_research_workflow_block():
    source = (PROJECT_ROOT / "core" / "context" / "adapters.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "_MARKER_RESEARCH_WORKFLOW = \"[RESEARCH WORKFLOW]\"" in source
    assert "research_workflow: str = \"\"" in source
    assert "_add_marked(inputs, research_workflow, _MARKER_RESEARCH_WORKFLOW)" in source
