"""
Integration tests for verified distillation (Phase M8).

Verifies:
  I5: build_verified_candidate includes tool_cross_reference.
  I5b: verify_distillation_candidate correctly cross-references with ledger.
  I5c: Proposed candidates are refused for write; executed are allowed.
  I5d: Preview output includes verification_status field.

Phase M8 — distillation verification preview. No inbox writes tested.

Usage:
    pytest tests/integration/test_distillation_verified.py -v
"""

import json
import os
import sys
import tempfile
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

pytestmark = skip_if_py_too_old


# ═══ Fixtures ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _enable_ledger():
    """Enable the ledger env var for cross-reference tests."""
    old_ledger = os.environ.get("GA_TOOL_EVENT_LEDGER", "")
    old_distill = os.environ.get("GA_OPENAI_DISTILLATION", "")
    os.environ["GA_TOOL_EVENT_LEDGER"] = "1"
    os.environ["GA_OPENAI_DISTILLATION"] = "preview"
    yield
    if old_ledger:
        os.environ["GA_TOOL_EVENT_LEDGER"] = old_ledger
    else:
        os.environ.pop("GA_TOOL_EVENT_LEDGER", None)
    if old_distill:
        os.environ["GA_OPENAI_DISTILLATION"] = old_distill
    else:
        os.environ.pop("GA_OPENAI_DISTILLATION", None)


# ═══ I5: Verified candidate ═════════════════════════════════════════════════

def test_build_verified_candidate_includes_cross_reference():
    """I5: build_verified_candidate includes tool_cross_reference field."""
    from core.memory.distillation import build_verified_candidate

    candidate = build_verified_candidate(
        summary="Added auth module with tests",
        source="openai",
        run_id="test-run-1",
        files_touched=["core/auth.py", "tests/test_auth.py"],
    )

    assert "tool_cross_reference" in candidate
    ref = candidate["tool_cross_reference"]
    assert "verified" in ref
    assert "matched_events" in ref
    assert "ledger_available" in ref


def test_verify_with_ledger_finds_matching_files():
    """I5b: Cross-reference matches files_touched against tool event paths."""
    from core.memory.distillation import build_distillation_candidate, verify_distillation_candidate
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_write", {"path": "core/auth.py"}, target_path="core/auth.py", turn=1)
    ledger.complete_call(eid, result="File written", status="success")
    eid2 = ledger.start_call("file_write", {"path": "tests/test_auth.py"}, target_path="tests/test_auth.py", turn=1)
    ledger.complete_call(eid2, result="File written", status="success")

    candidate = build_distillation_candidate(
        summary="Added auth module",
        files_touched=["core/auth.py", "tests/test_auth.py", "README.md"],
    )

    verified = verify_distillation_candidate(candidate, tool_event_ledger=ledger)
    ref = verified["tool_cross_reference"]

    assert ref["verified"] is True
    assert "core/auth.py" in ref["matched_files"]
    assert "tests/test_auth.py" in ref["matched_files"]
    assert "README.md" in ref["unmatched_files"]


def test_verify_with_ledger_does_not_verify_unmatched_files():
    """A tool event for a.py must not verify a candidate that claims b.py."""
    from core.memory.distillation import build_distillation_candidate, verify_distillation_candidate
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_write", {"path": "a.py"}, target_path="a.py", turn=1)
    ledger.complete_call(eid, result="File written", status="success")

    candidate = build_distillation_candidate(
        summary="Claims b.py was changed",
        files_touched=["b.py"],
    )

    verified = verify_distillation_candidate(candidate, tool_event_ledger=ledger)
    ref = verified["tool_cross_reference"]

    assert ref["verified"] is False
    assert ref["matched_files"] == []
    assert ref["unmatched_files"] == ["b.py"]


def test_verify_without_ledger_marks_unverified():
    """Without ledger, verification is NOT_CHECKED."""
    from core.memory.distillation import build_distillation_candidate, verify_distillation_candidate

    candidate = build_distillation_candidate(summary="Some change")
    verified = verify_distillation_candidate(candidate, tool_event_ledger=None)

    ref = verified["tool_cross_reference"]
    assert ref["verified"] is False
    assert ref["ledger_available"] is False


def test_verify_with_classifier():
    """I5b: Cross-reference with ChangeClassifier detects executed changes."""
    from core.memory.distillation import build_distillation_candidate, verify_distillation_candidate
    from core.context.change_classifier import ChangeClassifier

    classifier = ChangeClassifier()
    classifier.record_executed("Wrote auth module", turn=1)

    candidate = build_distillation_candidate(summary="Added auth module")
    verified = verify_distillation_candidate(candidate, change_classifier=classifier)

    ref = verified["tool_cross_reference"]
    assert ref["verified"] is True
    assert ref["classifier_executed"] == 1


# ═══ I5c: Proposed vs Executed ═════════════════════════════════════════════

def test_proposed_candidate_refused_for_write():
    """I5c: Proposed candidates (is_proposed=True) are refused by write gate."""
    from core.memory.distillation import build_distillation_candidate, write_distillation_candidate

    candidate = build_distillation_candidate(
        summary="Plan to refactor auth",
        is_proposed=True,
    )

    with tempfile.TemporaryDirectory() as tmp:
        result = write_distillation_candidate(candidate, project_root=tmp)
        assert not result["written"]
        assert "refused" in result["reason"] or "proposed" in result["reason"].lower()


def test_executed_candidate_allowed_for_preview():
    """I5c: Executed candidates (is_proposed=False) proceed to preview."""
    from core.memory.distillation import build_distillation_candidate, write_distillation_candidate

    candidate = build_distillation_candidate(
        summary="Wrote auth.py with tests",
        is_proposed=False,
    )

    with tempfile.TemporaryDirectory() as tmp:
        result = write_distillation_candidate(candidate, project_root=tmp)
        assert result["mode"] == "preview"
        assert "preview" in result["reason"]
        # Should have written to preview dir
        if result["path"]:
            assert os.path.exists(result["path"])


# ═══ I5d: Preview output ═══════════════════════════════════════════════════

def test_preview_includes_verification_status():
    """I5d: Preview JSON includes verification_status field."""
    from core.memory.distillation import build_verified_candidate, write_distillation_candidate
    from core.context.tool_event_ledger import ToolEventLedger

    ledger = ToolEventLedger()
    eid = ledger.start_call("file_write", {"path": "auth.py"}, target_path="auth.py", turn=1)
    ledger.complete_call(eid, result="done", status="success")

    candidate = build_verified_candidate(
        summary="Added auth",
        files_touched=["auth.py"],
        tool_event_ledger=ledger,
    )

    with tempfile.TemporaryDirectory() as tmp:
        result = write_distillation_candidate(candidate, project_root=tmp)
        if result["path"] and os.path.exists(result["path"]):
            with open(result["path"], "r", encoding="utf-8") as f:
                data = json.load(f)

            assert "verification_status" in data
            assert data["verification_status"] == "VERIFIED"
            assert "tool_cross_reference" in data
            assert data["tool_cross_reference"]["verified"] is True


def test_format_inbox_entry_excludes_proposed():
    """format_inbox_entry returns empty string for proposed candidates."""
    from core.memory.distillation import format_inbox_entry

    candidate = {"title": "Test", "summary": "test", "is_proposed": True}
    result = format_inbox_entry(candidate)
    assert result == ""


def test_format_inbox_entry_includes_files():
    """format_inbox_entry includes files_touched section."""
    from core.memory.distillation import format_inbox_entry

    candidate = {
        "title": "Test",
        "summary": "Test summary",
        "source": "test",
        "run_id": "r1",
        "session": "s1",
        "task": "test task",
        "files_touched": ["a.py", "b.py"],
        "questions": ["What to test?"],
        "is_proposed": False,
        "generated_at": "2026-01-01T00:00:00",
    }

    result = format_inbox_entry(candidate)
    assert "a.py" in result
    assert "b.py" in result
    assert "What to test?" in result


# ═══ Mode gate ═════════════════════════════════════════════════════════════

def test_get_distillation_mode_defaults_to_preview():
    """Default mode is preview."""
    from core.memory.distillation import get_distillation_mode
    old = os.environ.pop("GA_OPENAI_DISTILLATION", None)
    try:
        assert get_distillation_mode() == "preview"
    finally:
        if old:
            os.environ["GA_OPENAI_DISTILLATION"] = old
