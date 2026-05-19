"""Tests for AgentOutputEvent — the canonical output event type."""

import pytest
from core.protocol.events import AgentOutputEvent


class TestAgentOutputEventCreation:
    """Direct construction."""

    def test_chunk_event(self):
        ev = AgentOutputEvent(kind="chunk", text="hello", turn=1)
        assert ev.kind == "chunk"
        assert ev.text == "hello"
        assert ev.turn == 1
        assert not ev.is_terminal()

    def test_done_event(self):
        ev = AgentOutputEvent(kind="done", text="final response", turn=3)
        assert ev.kind == "done"
        assert ev.is_terminal()

    def test_stopped_event(self):
        ev = AgentOutputEvent(kind="stopped", text="partial...")
        assert ev.is_terminal()

    def test_error_event(self):
        ev = AgentOutputEvent(kind="error", error="something broke")
        assert ev.is_terminal()
        assert ev.error == "something broke"

    def test_turn_events_not_terminal(self):
        for kind in ("turn_start", "turn_end", "turn_delta"):
            ev = AgentOutputEvent(kind=kind)
            assert not ev.is_terminal()

    def test_metadata_stored(self):
        ev = AgentOutputEvent(kind="done", text="x",
                              metadata={"shortcut_type": "read_shortcut"})
        assert ev.metadata["shortcut_type"] == "read_shortcut"


class TestFromLegacyDict:
    """Conversion from legacy raw-dict queue items."""

    def test_legacy_next(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"next": "streaming text", "source": "user", "turn": 2, "task_id": "abc"}
        )
        assert ev.kind == "chunk"
        assert ev.text == "streaming text"
        assert ev.source == "user"
        assert ev.turn == 2
        assert ev.task_id == "abc"

    def test_legacy_done(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"done": "final", "source": "user", "turn": 1, "task_id": "xyz"}
        )
        assert ev.kind == "done"
        assert ev.text == "final"
        assert ev.is_terminal()

    def test_legacy_stopped(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"event": "stopped", "next": "partial output", "turn": 2}
        )
        assert ev.kind == "stopped"
        assert ev.text == "partial output"
        assert ev.is_terminal()

    def test_legacy_error(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"event": "error", "error": "connection failed", "turn": 1}
        )
        assert ev.kind == "error"
        assert ev.error == "connection failed"
        assert ev.is_terminal()

    def test_legacy_turn_start(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"event": "turn_start", "turn": 3, "source": "user"}
        )
        assert ev.kind == "turn_start"
        assert ev.turn == 3

    def test_legacy_turn_end(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"event": "turn_end", "turn": 3, "source": "user"}
        )
        assert ev.kind == "turn_end"

    def test_legacy_final_event_becomes_done(self):
        ev = AgentOutputEvent.from_legacy_dict(
            {"event": "final", "done": "complete", "turn": 5}
        )
        assert ev.kind == "done"
        assert ev.text == "complete"

    def test_legacy_shortcut_metadata_preserved(self):
        ev = AgentOutputEvent.from_legacy_dict({
            "done": "result",
            "final_answer_ready": True,
            "shortcut_type": "read_shortcut",
            "shortcut_confidence": 0.95,
            "tool_error": False,
        })
        assert ev.metadata["final_answer_ready"] is True
        assert ev.metadata["shortcut_type"] == "read_shortcut"
        assert ev.metadata["shortcut_confidence"] == 0.95

    def test_unknown_shape_defaults_to_chunk(self):
        ev = AgentOutputEvent.from_legacy_dict({"unknown_key": "value"})
        assert ev.kind == "chunk"
        assert ev.text == ""


class TestToLegacyDict:
    """Round-trip conversion back to legacy dict format."""

    def test_chunk_roundtrip(self):
        ev = AgentOutputEvent(kind="chunk", text="hi", source="u", turn=1, task_id="t1")
        d = ev.to_legacy_dict()
        assert d["next"] == "hi"
        assert d["source"] == "u"
        assert d["turn"] == 1
        assert d["task_id"] == "t1"

    def test_done_roundtrip(self):
        ev = AgentOutputEvent(kind="done", text="bye", source="u", turn=2)
        d = ev.to_legacy_dict()
        assert d["done"] == "bye"

    def test_stopped_roundtrip(self):
        ev = AgentOutputEvent(kind="stopped", text="partial")
        d = ev.to_legacy_dict()
        assert d["event"] == "stopped"
        assert d["next"] == "partial"

    def test_error_roundtrip(self):
        ev = AgentOutputEvent(kind="error", error="boom")
        d = ev.to_legacy_dict()
        assert d["event"] == "error"
        assert d["error"] == "boom"
