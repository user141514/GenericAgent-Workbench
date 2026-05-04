"""Integration test: E2E routing pipeline (P2-5).

Tests the full chain: RouterRules → skill selection → policy build → evaluation,
without requiring real LLM calls.
"""

import os

import pytest

from core.router_rules import RouterRules
from core.skills.skill_effects import SkillEffects
from core.skills.skill_registry import SkillRegistry, SkillSpec
from core.runtime.execution_policy import (
    ExecutionPolicy,
    build_execution_policy_from_skills,
    evaluate_operation,
    get_policy_mode,
)
from core.runtime.read_prefetch import (
    detect_read_prefetch,
    safe_read_prefetch_content,
    build_read_prefetch_context,
)


@pytest.fixture
def registry_with_security_skill():
    """A registry with a single security skill that disables shell_exec."""
    reg = SkillRegistry()
    effects = SkillEffects(disable_tools=["shell_exec", "code_run"], max_turns=10)
    spec = SkillSpec(
        name="security_gate",
        category="security",
        description="Blocks dangerous tools",
        triggers=["危险操作", "shell", "安装"],
        negative_triggers=[],
        source_url="",
        file_path="/fake/security_gate.md",
        applies_to=["planner", "executor"],
        effects=effects,
    )
    reg.register_skill(spec)
    return reg


class TestE2ERoutingPipeline:
    """RouterRules → skill activation → policy → evaluation."""

    def test_chat_query_routes_correctly(self):
        result = RouterRules.match("你好")
        assert result.target in ("chat", None)

    def test_code_query_routes_to_executor(self):
        result = RouterRules.match("帮我写一个快速排序")
        assert result.target in ("code", "executor")

    def test_review_query_routes_to_review(self):
        result = RouterRules.match("审查 core/router_rules.py 的代码")
        assert result.target in ("review", "executor")

    def test_research_query_routes_to_research(self):
        result = RouterRules.match("查一下 Python 3.12 的新特性")
        assert result.target in ("research", "executor")

    def test_skill_policy_builds_correctly(self, registry_with_security_skill):
        policy = build_execution_policy_from_skills(
            ["security_gate"], registry_with_security_skill, phase="planner"
        )
        assert "shell_exec" in policy.disabled_tools
        assert "code_run" in policy.disabled_tools
        assert policy.max_turns == 10
        assert "security_gate" in policy.source_skills

    def test_skill_policy_flows_to_evaluation(self, registry_with_security_skill):
        policy = build_execution_policy_from_skills(
            ["security_gate"], registry_with_security_skill, phase="planner"
        )
        policy_dict = {
            "source_skills": policy.source_skills,
            "disabled_tools": list(policy.disabled_tools),
            "max_turns": policy.max_turns,
            "warnings": policy.warnings,
        }
        decision = evaluate_operation(
            "运行 shell 命令", "pip install requests", policy=policy_dict
        )
        assert any("disabled_tools" in m for m in decision.matched_patterns)

    def test_unknown_skill_produces_warning(self, registry_with_security_skill):
        policy = build_execution_policy_from_skills(
            ["nonexistent_skill"], registry_with_security_skill, phase="planner"
        )
        assert len(policy.warnings) > 0


class TestHandoffPipeline:
    """Planner → classic executor handoff artifacts."""

    def test_executor_plan_contains_reason(self):
        from core.openai_agentmain import _classic_executor_plan

        plan = _classic_executor_plan("test orchestration failure")
        assert "GenericAgent" in plan
        assert "test orchestration failure" in plan

    def test_executor_plan_handles_empty_reason(self):
        from core.openai_agentmain import _classic_executor_plan

        plan = _classic_executor_plan("")
        assert "GenericAgent" in plan

    def test_should_fallback_to_classic_for_executor_targets(self):
        from core.openai_agentmain import _should_fallback_to_classic

        # Executor targets with an exception that mentions handoff/tool should fall back
        for target in ("executor", "code", "review", "research"):
            assert _should_fallback_to_classic(target, exc=RuntimeError("tool call failed")) is True

    def test_should_not_fallback_for_chat(self):
        from core.openai_agentmain import _should_fallback_to_classic

        assert _should_fallback_to_classic("chat_specialist") is False


class TestPrefetchPipeline:
    """Detection → safe read → context builder (P2-1 integration)."""

    def test_full_pipeline_with_real_file(self, tmp_path):
        (tmp_path / "demo_module.py").write_text(
            "def hello():\n    return 'world'\n\nclass Foo:\n    pass\n", encoding="utf-8"
        )
        decision = detect_read_prefetch("分析 demo_module.py 的代码结构", project_root=tmp_path)
        assert decision.should_prefetch is True
        assert decision.target_file == "demo_module.py"

        content, status, meta = safe_read_prefetch_content(
            decision.target_file, tmp_path, max_lines=200, max_chars=12000
        )
        assert status == "ok"
        assert content is not None
        assert "def hello" in content

        context = build_read_prefetch_context(
            content, decision.target_file, decision.reason, decision.confidence, bool(meta.get("truncated"))
        )
        assert "[READ PREFETCH CONTEXT]" in context
        assert "demo_module.py" in context
        assert "def hello" in context

    def test_pipeline_skips_sensitive_file(self, tmp_path):
        (tmp_path / ".env").write_text("SECRET=xxx", encoding="utf-8")
        # Detection won't trigger on ".env" because it's not wrapped in quotes/paths
        # but safe_read should skip it regardless
        content, status, _ = safe_read_prefetch_content(".env", tmp_path)
        assert status == "sensitive_path"
        assert content is None

    def test_pipeline_skips_large_file(self, tmp_path):
        big_file = tmp_path / "big.py"
        big_file.write_bytes(b"x" * 600_000)  # > 512KB
        content, status, meta = safe_read_prefetch_content("big.py", tmp_path)
        assert status == "file_too_large"
        assert content is None

    def test_prefetch_not_injected_for_non_analysis(self, tmp_path):
        (tmp_path / "notes.md").write_text("# Notes\ncontent", encoding="utf-8")
        decision = detect_read_prefetch("修改 notes.md 的内容", project_root=tmp_path)
        assert decision.should_prefetch is False
