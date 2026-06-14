from core.api.frontier_bridge import build_frontier_state_event, create_frontier_run_state
from core.protocol.events import AgentOutputEvent


def test_frontier_bridge_skips_plain_chat():
    frontier = create_frontier_run_state("hello, what can you do?", "auto")

    assert frontier.enabled is False
    assert build_frontier_state_event("run_1", frontier) is None


def test_frontier_bridge_emits_structured_side_channel_event():
    frontier = create_frontier_run_state(
        "Audit manuscript versions and check the benchmark claim.",
        "auto",
    )

    event = build_frontier_state_event(
        "run_1",
        frontier,
        AgentOutputEvent(kind="chunk", text="Strategy diagnosis: compare versions.", turn=2),
    )

    assert event is not None
    assert event.kind == "frontier_state"
    assert event.turn == 2
    assert event.metadata["frontier_state"]["enabled"] is True
    assert frontier.latest_snapshot == event.metadata["frontier_state"]


def test_frontier_bridge_does_not_echo_frontier_events():
    frontier = create_frontier_run_state("failed benchmark research strategy", "auto")

    assert build_frontier_state_event(
        "run_1",
        frontier,
        AgentOutputEvent(kind="frontier_state", metadata={"frontier_state": {"enabled": True}}),
    ) is None
