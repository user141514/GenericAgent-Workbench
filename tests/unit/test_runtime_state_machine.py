import pytest

from core.runtime.state_machine import (
    IllegalModeTransition,
    ModeStateMachine,
    mode_for_route,
)


def test_mode_for_route_maps_direct_answer_and_code_paths():
    assert mode_for_route("chat", "single_agent") == "direct_answer"
    assert mode_for_route("executor", "single_agent") == "code"
    assert mode_for_route("review", "single_agent") == "code"
    assert mode_for_route("executor", "multi_agent") == "code"
    assert mode_for_route(None, "single_agent") == "plan"


def test_state_machine_accepts_expected_runtime_flow():
    machine = ModeStateMachine()

    assert machine.transition("plan") == ("idle", "plan")
    assert machine.transition("code") == ("plan", "code")
    assert machine.transition("review") == ("code", "review")
    assert machine.transition("completed") == ("review", "completed")


def test_state_machine_supports_stop_and_recovery_flow():
    machine = ModeStateMachine(current_mode="code")

    assert machine.transition("stopped") == ("code", "stopped")
    assert machine.transition("recovery") == ("stopped", "recovery")
    assert machine.transition("code") == ("recovery", "code")


def test_state_machine_rejects_illegal_transition():
    machine = ModeStateMachine(current_mode="idle")

    with pytest.raises(IllegalModeTransition):
        machine.transition("completed")


def test_state_machine_allows_same_mode_noop():
    machine = ModeStateMachine(current_mode="review")

    assert machine.transition("review") == ("review", "review")
