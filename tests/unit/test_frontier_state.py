from core.quality.execution_honesty import ExecutionState, StateDelta
from core.quality.frontier_state import (
    build_frontier_state_snapshot,
    frontier_state_should_activate,
)


def test_frontier_state_snapshot_is_serializable_for_research_task():
    snapshot = build_frontier_state_snapshot(
        user_input="We need a research strategy after failed benchmark experiments.",
        route_target="research",
        response_text=(
            "Strategy diagnosis: the bottleneck is support leakage. "
            "Minimal experiment ladder: run a kill test first. "
            "Failure ledger: record hypothesis and observed result. "
            "Evidence vs hypothesis: logs are evidence and prior is hypothesis. "
            "Frontier relay: inspect split leakage next."
        ),
        execution_state=ExecutionState(state_delta=StateDelta(metrics_verified=True)),
    )

    data = snapshot.to_dict()

    assert data["enabled"] is True
    assert data["intent_state"]["task_type"] == "research_frontier"
    assert data["execution_state"]["state_delta"]["metrics_verified"] is True
    assert data["strategy_state"]["candidates"]
    assert data["confidence_state"]["next_verification"]


def test_frontier_state_triggers_research_and_audit_but_not_plain_tasks():
    assert frontier_state_should_activate(
        "Turn failed benchmark evidence into a research strategy.",
        "research",
    )
    assert frontier_state_should_activate(
        "Audit the manuscript versions and check whether the claim is innovative.",
        "review",
    )
    assert frontier_state_should_activate(
        "Audit the manuscript versions and check whether the claim is innovative.",
        "auto",
    )

    assert not frontier_state_should_activate("hello, what can you do?", "chat")
    assert not frontier_state_should_activate("fix this pytest failure in foo.py", "code")
    assert not frontier_state_should_activate("review this PR for naming style", "auto")
    assert not frontier_state_should_activate("read README first line", "executor")


def test_frontier_state_marks_strong_claim_without_counterevidence_as_warning():
    snapshot = build_frontier_state_snapshot(
        user_input="Decide whether this algorithm has innovation.",
        route_target="research",
        response_text=(
            "Strategy diagnosis: this is merely incremental and has no innovation. "
            "Baseline: compare to the strongest baseline. "
            "Minimal experiment ladder: run a kill test first. "
            "Failure ledger: record hypothesis and observed result. "
            "Evidence vs hypothesis: logs are evidence and prior is hypothesis. "
            "Frontier relay: inspect baseline next."
        ),
    )

    flags = snapshot.synthesis_state.get("warnings", [])

    assert "missing_counterevidence_for_strong_claim" in flags
    assert snapshot.synthesis_state["gate_action"] == "review_warn"
    assert snapshot.confidence_state["current_judgment"] in {"low", "medium"}


def test_frontier_state_marks_missing_version_map_as_warning():
    snapshot = build_frontier_state_snapshot(
        user_input="Audit old_dir and new_dir before deciding the manuscript claim.",
        route_target="review",
        response_text=(
            "Strategy diagnosis: compare both folders. "
            "Baseline: compare to current baseline. "
            "Minimal experiment ladder: run a shared smoke test first. "
            "Failure ledger: record hypothesis and observed result. "
            "Evidence vs hypothesis: files are evidence and prior is hypothesis. "
            "Frontier relay: inspect shared metric next."
        ),
    )

    assert "missing_version_map" in snapshot.synthesis_state["warnings"]
