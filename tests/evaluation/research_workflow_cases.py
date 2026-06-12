from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResearchWorkflowCase:
    id: str
    prompt: str
    expected_trigger: bool
    required_sections: list[str] = field(default_factory=list)
    difficulty: str = "medium"
    control_type: str = "positive"


REQUIRED_WORKFLOW_SECTIONS = [
    "Strategy Kernel",
    "Minimal Experiment Ladder",
    "Failure Ledger",
    "Evidence Precedence",
    "Frontier Relay",
    "Adversarial Review",
]


RESEARCH_WORKFLOW_CASES = [
    ResearchWorkflowCase(
        id="positive-open-innovation",
        prompt=(
            "Turn this open-ended algorithm innovation problem into a research workflow "
            "with strategy diagnosis, kill tests, and frontier relay."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="medium",
        control_type="positive",
    ),
    ResearchWorkflowCase(
        id="positive-failed-experiments",
        prompt=(
            "Three experiments failed against a strong baseline. Build a failure ledger "
            "and choose the next minimal experiment."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="complex",
        control_type="positive",
    ),
    ResearchWorkflowCase(
        id="positive-claim-pivot",
        prompt=(
            "The algorithm does not beat the benchmark but reveals a mechanism. "
            "Decide whether the paper claim should pivot."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="complex",
        control_type="positive",
    ),
    ResearchWorkflowCase(
        id="positive-system-dynamics",
        prompt=(
            "Use system dynamics to analyze why this research process keeps producing "
            "fragile big experiments instead of robust small tests."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="medium",
        control_type="positive",
    ),
    ResearchWorkflowCase(
        id="hard-evidence-conflict",
        prompt=(
            "My prior says learned ranking should win, but the latest benchmark logs "
            "show frequency baseline dominates. What strategy should we choose?"
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="complex",
        control_type="hard",
    ),
    ResearchWorkflowCase(
        id="hard-negative-result",
        prompt=(
            "A negative result killed the proposed model but may support a mechanism paper. "
            "Design the next diagnostic ladder."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS),
        difficulty="complex",
        control_type="hard",
    ),
    ResearchWorkflowCase(
        id="hard-version-map",
        prompt=(
            "Audit the old_dir and new_dir versions of this manuscript before deciding "
            "whether the algorithm claim is real innovation or just incremental."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS) + ["Version Map", "Strong Counterevidence Check"],
        difficulty="complex",
        control_type="hard",
    ),
    ResearchWorkflowCase(
        id="hard-strong-conclusion",
        prompt=(
            "The latest benchmark suggests this may be a dead feature with no innovation. "
            "Check the strongest counterevidence before making the research decision."
        ),
        expected_trigger=True,
        required_sections=list(REQUIRED_WORKFLOW_SECTIONS) + ["Strong Counterevidence Check"],
        difficulty="complex",
        control_type="hard",
    ),
    ResearchWorkflowCase(
        id="negative-chat",
        prompt="Hello, what can you do?",
        expected_trigger=False,
        difficulty="simple",
        control_type="negative",
    ),
    ResearchWorkflowCase(
        id="negative-plain-code",
        prompt="Fix this pytest failure in core/router_rules.py.",
        expected_trigger=False,
        difficulty="simple",
        control_type="negative",
    ),
    ResearchWorkflowCase(
        id="negative-read-file",
        prompt="Read README first line and answer in one sentence.",
        expected_trigger=False,
        difficulty="simple",
        control_type="negative",
    ),
    ResearchWorkflowCase(
        id="negative-review",
        prompt="Review this PR for security issues.",
        expected_trigger=False,
        difficulty="medium",
        control_type="negative",
    ),
]


__all__ = [
    "REQUIRED_WORKFLOW_SECTIONS",
    "RESEARCH_WORKFLOW_CASES",
    "ResearchWorkflowCase",
]
