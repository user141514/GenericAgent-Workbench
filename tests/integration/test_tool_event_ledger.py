"""
Integration tests for Tool Event Ledger + Change Classifier (Phase M7).

Verifies:
  I5: Tool events are correctly recorded (start_call + complete_call).
  T5: ChangeClassifier separates proposed from executed changes.
  I5b: Ledger is safe under concurrent/error conditions.
  I5c: Recent summary produces valid format.

Phase M7 — ledger and classifier validation. No runtime integration tested.

Usage:
    pytest tests/integration/test_tool_event_ledger.py -v
"""

import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_MIN_PYTHON = (3, 10)
_py_version = sys.version_info[:2]
CAN_LOAD = _py_version >= _MIN_PYTHON

skip_if_py_too_old = pytest.mark.skipif(
    not CAN_LOAD,
    reason=f"Python {'.'.join(map(str, _MIN_PYTHON))}+ required. Current: {sys.version}",
)

# Apply to all test functions that import core.context modules
pytestmark = skip_if_py_too_old


# ═══ Helpers ════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _enable_ledger():
    """Enable the ledger env var for all tests in this module."""
    old = os.environ.get("GA_TOOL_EVENT_LEDGER", "")
    os.environ["GA_TOOL_EVENT_LEDGER"] = "1"
    yield
    if old:
        os.environ["GA_TOOL_EVENT_LEDGER"] = old
    else:
        os.environ.pop("GA_TOOL_EVENT_LEDGER", None)


# ═══ I5: Tool Event Ledger ═════════════════════════════════════════════════

def test_ledger_disabled_by_default():
    """Without env var, recording is a no-op."""
    old = os.environ.pop("GA_TOOL_EVENT_LEDGER", None)
    try:
        from core.context.tool_event_ledger import ToolEventLedger, tool_event_ledger_enabled
        assert not tool_event_ledger_enabled()
        ledger = ToolEventLedger()
        eid = ledger.start_call("file_read", {"path": "test.txt"})
        assert eid == ""
    finally:
        if old:
            os.environ["GA_TOOL_EVENT_LEDGER"] = old


def test_start_and_complete_call():
    """I5: Basic start_call + complete_call cycle."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_read", {"path": "test.txt"}, turn=1, index=0)
    assert eid != ""

    ledger.complete_call(eid, result="file content here", status="success")
    events = ledger.recent_events()
    assert len(events) == 1

    e = events[0]
    assert e.tool_name == "file_read"
    assert e.status == "success"
    assert e.turn == 1
    assert e.args_summary == "path=test.txt"


def test_multiple_events_ordered():
    """Events are recorded in order."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    for i in range(5):
        eid = ledger.start_call(f"tool_{i}", {}, turn=1, index=i)
        ledger.complete_call(eid, result=f"result_{i}")

    events = ledger.recent_events()
    assert len(events) == 5
    assert [e.tool_name for e in events] == [f"tool_{i}" for i in range(5)]


def test_max_events_enforced():
    """Old events are trimmed when max_events is exceeded."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger(max_events=5)
    for i in range(10):
        eid = ledger.start_call(f"tool_{i}", {}, turn=1, index=i)
        ledger.complete_call(eid, result=f"result_{i}")

    events = ledger.recent_events()
    assert len(events) == 5
    # Should be the last 5
    assert events[0].tool_name == "tool_5"


def test_error_events():
    """Error events are tracked separately."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid1 = ledger.start_call("good_tool", {}, turn=1, index=0)
    eid2 = ledger.start_call("bad_tool", {}, turn=1, index=1)
    ledger.complete_call(eid1, result="ok", status="success")
    ledger.complete_call(eid2, result="error output", status="error", error_like=True)

    errors = ledger.error_events()
    assert len(errors) == 1
    assert errors[0].tool_name == "bad_tool"


def test_pending_count():
    """Uncompleted calls are tracked as pending."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    ledger.start_call("tool_a", {}, turn=1, index=0)
    ledger.start_call("tool_b", {}, turn=1, index=1)
    assert ledger.pending_count() == 2

    eid = ledger.start_call("tool_c", {}, turn=1, index=2)
    ledger.complete_call(eid, result="done")
    assert ledger.pending_count() == 2  # a and b still pending


def test_recent_summary_format():
    """I5c: recent_summary() produces valid text format."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_read", {"path": "test.txt"}, turn=1, index=0)
    ledger.complete_call(eid, result="Hello World", status="success")

    summary = ledger.recent_summary()
    assert "[TOOL EVENT LEDGER" in summary
    assert "file_read" in summary
    assert "[/TOOL EVENT LEDGER" in summary


def test_ledger_clear():
    """clear() resets the ledger."""
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("tool", {}, turn=1, index=0)
    ledger.complete_call(eid, result="done")
    assert len(ledger.recent_events()) == 1

    ledger.clear()
    assert len(ledger.recent_events()) == 0
    assert ledger.pending_count() == 0


# ═══ T5: Change Classifier ═════════════════════════════════════════════════

def test_classifier_records_proposal():
    """T5: Proposals are recorded separately from executed changes."""
    from core.context.change_classifier import ChangeClassifier
    from core.context.tool_event_ledger import ToolEventLedger

    classifier = ChangeClassifier()
    ledger = ToolEventLedger()

    # Record a proposal
    pid = classifier.record_proposal("Refactor auth module", source="plan", turn=1)
    assert pid != ""

    pending = classifier.get_pending()
    assert len(pending) == 1
    assert pending[0].summary == "Refactor auth module"
    assert pending[0].change_type == "proposed"
    assert not pending[0].verified


def test_classifier_records_executed():
    """Executed changes are confirmed by tool evidence."""
    from core.context.change_classifier import ChangeClassifier

    classifier = ChangeClassifier()
    classifier.record_executed(
        "Wrote auth_test.py",
        tool_event_ids=["file_write_1_0_1234"],
        turn=1,
    )

    executed = classifier.get_executed()
    assert len(executed) == 1
    assert executed[0].summary == "Wrote auth_test.py"
    assert executed[0].verified
    assert executed[0].change_type == "executed"


def test_classifier_verify_against_ledger():
    """T5b: verify_against_ledger cross-references proposals with tool events."""
    from core.context.change_classifier import ChangeClassifier
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_write", {"path": "auth.py"}, turn=1, index=0)
    ledger.complete_call(eid, result="wrote file", status="success")

    classifier = ChangeClassifier()
    classifier.record_proposal("Add auth module", source="plan", turn=1)
    classifier.record_proposal("Add tests", source="plan", turn=1)

    count = classifier.verify_against_ledger(ledger)
    assert count >= 1  # at least one proposal verified

    pending = classifier.get_pending()
    # After verification, proposals with tool evidence are verified
    verified = [p for p in classifier._proposals if p.verified]
    assert len(verified) >= 1


def test_classifier_summary():
    """classifier.summary() produces valid text format."""
    from core.context.change_classifier import ChangeClassifier

    classifier = ChangeClassifier()
    classifier.record_proposal("Add feature X", source="plan", turn=1)
    classifier.record_executed("Wrote feature_x.py", turn=1)

    summary = classifier.summary()
    assert "[CHANGE CLASSIFIER]" in summary
    assert "Executed" in summary
    assert "Pending" in summary
    assert "[/CHANGE CLASSIFIER]" in summary


def test_classifier_max_records():
    """Old records are trimmed."""
    from core.context.change_classifier import ChangeClassifier

    classifier = ChangeClassifier(max_records=3)
    for i in range(10):
        classifier.record_proposal(f"Proposal {i}", source="plan", turn=1)

    # Should only keep last 3
    assert len(classifier._proposals) == 3
    assert classifier._proposals[0].summary == "Proposal 7"


def test_classifier_clear():
    """clear() resets both proposals and executed."""
    from core.context.change_classifier import ChangeClassifier

    classifier = ChangeClassifier()
    classifier.record_proposal("Test", turn=1)
    classifier.record_executed("Test done", turn=1)
    assert len(classifier._proposals) == 1
    assert len(classifier._executed) == 1

    classifier.clear()
    assert len(classifier._proposals) == 0
    assert len(classifier._executed) == 0


# ═══ Integration: Ledger + Classifier ══════════════════════════════════════

def test_ledger_to_classifier_flow():
    """Full flow: record tool events → classify changes → verify."""
    from core.context.tool_event_ledger import ToolEventLedger
    from core.context.change_classifier import ChangeClassifier

    ledger = ToolEventLedger()
    classifier = ChangeClassifier()

    # Phase 1: Agent proposes a change
    classifier.record_proposal("Write test_ga.py", source="plan", turn=1)
    classifier.record_proposal("Update README", source="plan", turn=1)

    # Phase 2: Agent executes tools
    e1 = ledger.start_call("file_write", {"path": "tests/test_ga.py"}, turn=1, index=0)
    ledger.complete_call(e1, result="File written successfully", status="success")

    # Phase 3: Verify proposals against tool execution
    verified = classifier.verify_against_ledger(ledger)
    assert verified >= 1

    # Phase 4: Record executed change with tool evidence
    classifier.record_executed(
        "Wrote tests/test_ga.py (50 lines)",
        tool_event_ids=[e1],
        turn=1,
    )

    # After execution, the relevant proposal should be verified
    pending = classifier.get_pending()
    executed = classifier.get_executed()
    assert len(executed) == 1
    # "Write test_ga.py" proposal should now be verified (tool evidence exists)
    verified_proposals = [p for p in classifier._proposals if p.verified]
    assert len(verified_proposals) >= 1
