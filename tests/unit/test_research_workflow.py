from __future__ import annotations

from core.quality.research_workflow import (
    build_research_workflow_context,
    research_workflow_enabled,
    score_research_workflow_response,
    should_inject_research_workflow,
)


def test_research_workflow_enabled_defaults_on(monkeypatch):
    monkeypatch.delenv("GENERIC_AGENT_RESEARCH_WORKFLOW", raising=False)

    assert research_workflow_enabled() is True


def test_open_research_strategy_query_triggers_workflow():
    query = (
        "We have failed three algorithm experiments against a strong baseline. "
        "Help me choose the next research strategy and minimal benchmark."
    )

    assert should_inject_research_workflow(query, route_target="research") is True

    context = build_research_workflow_context(query, route_target="research")
    block = context["block"]
    assert context["matched"] is True
    assert context["chars"] <= 1800
    assert context["required_sections"] == [
        "Strategy Kernel",
        "System Dynamics Lens",
        "Good/Bad Strategy Audit",
        "Minimal Experiment Ladder",
        "Failure Ledger",
        "Frontier Relay",
    ]
    assert "Strategy Kernel" in block
    assert "System Dynamics Lens" in block
    assert "Failure Ledger" in block
    assert "version_map" in block
    assert "adversarial_review" in block
    assert "exploration_steps" in block
    assert "Do not quote or summarize source books" in block


def test_research_workflow_excludes_simple_chat_and_plain_code():
    assert should_inject_research_workflow("hello, what can you do?", route_target="chat") is False
    assert should_inject_research_workflow("fix this pytest failure in foo.py", route_target="code") is False
    assert should_inject_research_workflow("read README first line", route_target="executor") is False
    assert should_inject_research_workflow("review this PR for security issues", route_target="review") is False


def test_research_workflow_can_rescue_misrouted_chat():
    query = "Turn this failed benchmark into a research strategy with kill tests."

    assert should_inject_research_workflow(query, route_target="chat") is True


def test_research_workflow_can_be_disabled(monkeypatch):
    monkeypatch.setenv("GENERIC_AGENT_RESEARCH_WORKFLOW", "0")

    context = build_research_workflow_context(
        "Design an algorithm innovation workflow with kill tests.",
        route_target="research",
    )

    assert research_workflow_enabled() is False
    assert context["matched"] is False
    assert context["block"] == ""
    assert context["reason"] == "research workflow gate disabled"


def test_research_workflow_honors_small_budget(monkeypatch):
    monkeypatch.setenv("GENERIC_AGENT_RESEARCH_WORKFLOW_MAX_CHARS", "500")

    context = build_research_workflow_context(
        "Plan an open-ended algorithm research program with failure ledgers.",
        route_target="research",
        max_chars=1800,
    )

    assert context["matched"] is True
    assert context["chars"] <= 500


def test_response_scorer_rewards_complete_research_workflow():
    response = """
    version_map: not applicable; only one benchmark artifact is under review.
    Strategy diagnosis: the current bottleneck is not model capacity but support leakage.
    Evidence vs hypothesis: the failed ablation and benchmark logs are evidence; my prior is only a hypothesis.
    Baseline: compare against frequency support, content-only, and learned blend baselines.
    Minimal experiment ladder: first run a kill test on hard negatives, then a medium ablation, then the full benchmark.
    Failure ledger: record experiment, intended hypothesis, observed result, failure type, and implication.
    adversarial_review: assume each conclusion is wrong; the strongest counterexample is that split leakage, not support leakage, explains the result.
    budget_gate: exploration_steps: 3; adversarial_review_steps: 1.
    Frontier relay: next handoff should inspect split leakage, implement the diagnostic, and exclude easy negatives.
    """

    score = score_research_workflow_response(
        "We need a research strategy after failed benchmark experiments.",
        response,
    )

    assert score.total >= 0.8
    assert score.missing_sections == []
    assert score.bad_strategy_flags == []
    assert score.section_scores["minimal_experiment"] == 1.0
    assert score.section_scores["failure_ledger"] == 1.0
    assert score.section_scores["evidence_precedence"] == 1.0
    assert score.section_scores["frontier_relay"] == 1.0
    assert score.section_scores["adversarial_review"] == 1.0
    assert score.section_scores["time_budget_gate"] == 1.0


def test_response_scorer_requires_version_map_for_multiple_versions():
    response = """
    Strategy diagnosis: the strongest claim is currently mixed across folders.
    Baseline: compare the old result and new result.
    Minimal experiment ladder: run a kill test on the smallest shared benchmark.
    Failure ledger: record hypothesis, observed result, failure type, and implication.
    Evidence vs hypothesis: files are evidence; my prior is a hypothesis.
    adversarial_review: assume each conclusion is wrong and look for the strongest counterexample.
    budget_gate: exploration_steps: 2; adversarial_review_steps: 1.
    Frontier relay: inspect the candidate folders, test the shared metric, exclude stale claims.
    """

    score = score_research_workflow_response(
        "Audit the two versions in old_dir/ and new_dir/ before deciding if the manuscript has innovation.",
        response,
    )

    assert score.section_scores["version_map"] == 0.0
    assert "Version Map" in score.missing_sections
    assert "missing_version_map" in score.bad_strategy_flags


def test_response_scorer_requires_counterevidence_for_strong_claims():
    response = """
    version_map: v1 is old and v2 is new.
    Strategy diagnosis: this is merely incremental and has no innovation.
    Baseline: compare to the strongest published baseline.
    Minimal experiment ladder: run a kill test before the full benchmark.
    Failure ledger: record hypothesis, observed result, failure type, and implication.
    Evidence vs hypothesis: benchmark logs are evidence and model prior is hypothesis.
    adversarial_review: assume each conclusion is wrong.
    budget_gate: exploration_steps: 2; adversarial_review_steps: 1.
    Frontier relay: inspect the baseline, test the diagnostic, exclude unsupported claims.
    """

    score = score_research_workflow_response(
        "Decide whether the algorithm paper is innovative.",
        response,
    )

    assert score.section_scores["counterevidence_check"] == 0.0
    assert "Strong Counterevidence Check" in score.missing_sections
    assert "missing_counterevidence_for_strong_claim" in score.bad_strategy_flags


def test_response_scorer_accepts_counterevidence_for_strong_claims():
    response = """
    version_map: v1 is old and v2 is new.
    Strategy diagnosis: the current result may be merely incremental.
    Strong counterevidence check: the strongest counterexample is that calibration changes the problem definition, not just the score.
    Baseline: compare to the strongest published baseline.
    Minimal experiment ladder: run a kill test before the full benchmark.
    Failure ledger: record hypothesis, observed result, failure type, and implication.
    Evidence vs hypothesis: benchmark logs are evidence and model prior is hypothesis.
    adversarial_review: assume each conclusion is wrong and search for the strongest counterexample.
    budget_gate: exploration_steps: 2; adversarial_review_steps: 1.
    Frontier relay: inspect the baseline, test the diagnostic, exclude unsupported claims.
    """

    score = score_research_workflow_response(
        "Decide whether the algorithm paper is innovative.",
        response,
    )

    assert score.section_scores["counterevidence_check"] == 1.0
    assert "missing_counterevidence_for_strong_claim" not in score.bad_strategy_flags


def test_response_scorer_blocks_final_when_exploration_has_no_adversarial_review():
    response = """
    version_map: not applicable.
    Strategy diagnosis: the bottleneck is evidence ordering.
    Baseline: compare the current benchmark baseline.
    Minimal experiment ladder: run a kill test first.
    Failure ledger: record hypothesis, observed result, failure type, and implication.
    Evidence vs hypothesis: logs are evidence and model prior is hypothesis.
    budget_gate: exploration_steps: 4; adversarial_review_steps: 0.
    Frontier relay: inspect logs, test diagnostic, exclude unsupported claims.
    """

    score = score_research_workflow_response(
        "We explored the benchmark and need a final research decision.",
        response,
    )

    assert score.section_scores["time_budget_gate"] == 0.0
    assert "Time Budget Gate" in score.missing_sections
    assert "missing_adversarial_review_after_exploration" in score.bad_strategy_flags


def test_response_scorer_penalizes_bad_strategy():
    response = (
        "We should build a better model and improve everything. "
        "This will be a comprehensive world-class solution."
    )

    score = score_research_workflow_response(
        "We need an algorithm research strategy after failed experiments.",
        response,
    )

    assert score.total < 0.35
    assert "missing_baseline" in score.bad_strategy_flags
    assert "missing_falsifiable_experiment" in score.bad_strategy_flags
    assert "generic_goal_language" in score.bad_strategy_flags
    assert "Minimal Experiment Ladder" in score.missing_sections
