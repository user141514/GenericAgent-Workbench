from __future__ import annotations

from core.quality.research_code_priority import (
    build_research_code_priority_context,
    should_inject_research_code_priority,
)


def test_code_route_injects_priority_guard():
    context = build_research_code_priority_context(
        "fix the failing pytest case",
        route_target="code",
    )

    assert context["matched"] is True
    assert context["chars"] <= 1200
    assert "model prior experience" in context["block"]
    assert "official docs" in context["block"]
    assert "verify with the narrowest meaningful test" in context["block"]


def test_research_query_prefers_traceable_evidence():
    context = build_research_code_priority_context(
        "搜索最新论文并比较 benchmark",
        route_target="research",
    )

    assert context["matched"] is True
    assert "fresh, authoritative, traceable evidence" in context["block"]
    assert "Separate verified facts from hypotheses" in context["block"]


def test_simple_read_excluded():
    assert should_inject_research_code_priority("读取 README 第一行", route_target="executor") is False
