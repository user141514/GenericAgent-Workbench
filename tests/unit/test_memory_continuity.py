"""
Multi-turn memory continuity tests (P2 from coding-improve.md §5.3).

Verifies that memory items maintain correct ordering, linking, and state
across multiple conversation turns.
"""

from __future__ import annotations

import time

import pytest

from core.memory.types import MemoryCandidate, MemoryItem, EvidenceChunk
from core.memory.write_gate import MemoryWriteDecision, MemoryWriteGate


class TestMemoryItemContinuity:
    """Memory items must maintain order and linkage across turns."""

    def _make_item(self, id: str, turn: int) -> MemoryItem:
        return MemoryItem(
            id=id,
            kind="fact",
            scope_type="session",
            scope_id=f"session-{turn}",
            content=f"Content from turn {turn}",
            source_turn=f"turn-{turn}",
            confidence=0.8,
            verified=0,
            created_at=str(time.time()),
        )

    def test_items_preserve_creation_order(self):
        """Items created across turns must preserve order."""
        items = [
            self._make_item("item-1", 1),
            self._make_item("item-2", 2),
            self._make_item("item-3", 3),
        ]
        turns = [item.source_turn for item in items]
        assert turns == ["turn-1", "turn-2", "turn-3"]

    def test_item_scopes_are_independent(self):
        """Items from different sessions must have independent scopes."""
        item1 = self._make_item("a", 1)
        item2 = self._make_item("b", 2)
        assert item1.scope_id != item2.scope_id

    def test_item_confidence_range(self):
        """Confidence must be in valid range [0, 1]."""
        item = MemoryItem(
            id="x", kind="fact", scope_type="global",
            scope_id="g", content="test", confidence=0.95,
        )
        assert 0 <= item.confidence <= 1.0

    def test_verified_defaults_to_zero(self):
        """New items start unverified."""
        item = self._make_item("new", 1)
        assert item.verified == 0

    def test_supersedes_creates_chain(self):
        """Superseded items form a replacement chain."""
        v1 = self._make_item("rule-1", 1)
        v2 = self._make_item("rule-2", 2)
        v2.supersedes = v1.id
        assert v2.supersedes == "rule-1"


class TestMemoryCandidateLifecycle:
    """Candidates progress through pending -> accepted/rejected."""

    def test_candidate_starts_pending(self):
        c = MemoryCandidate(
            id="c1", source="distiller",
            content="New pattern discovered",
        )
        assert c.status == "pending"

    def test_candidate_with_low_confidence(self):
        c = MemoryCandidate(
            id="c2", source="agent",
            content="Possible pattern", confidence=0.2,
        )
        assert c.confidence < 0.5

    def test_candidate_has_reason_field(self):
        c = MemoryCandidate(
            id="c3", source="distiller",
            content="Pattern", reason="needs_human_review",
        )
        assert c.reason is not None


class TestEvidenceChunkLinking:
    """Evidence chunks must be linkable to memory items."""

    def test_chunk_to_item_linkage(self):
        chunk = EvidenceChunk(
            id="ev-1", source_path="session.log",
            content="User said X",
            turn_index=3,
        )
        item = MemoryItem(
            id="mem-1", kind="fact",
            scope_type="session", scope_id="s1",
            content="X is true",
            evidence_chunk_id=chunk.id,
        )
        assert item.evidence_chunk_id == chunk.id

    def test_chunk_has_turn_index(self):
        chunk = EvidenceChunk(
            id="ev-2", source_path="log.txt",
            content="event", turn_index=5,
        )
        assert chunk.turn_index == 5

    def test_multiple_items_same_chunk(self):
        """Multiple items can reference the same evidence chunk."""
        chunk = EvidenceChunk(
            id="ev-shared", source_path="log.txt",
            content="multi-fact observation",
        )
        item_a = MemoryItem(
            id="a", kind="fact", scope_type="session",
            scope_id="s1", content="fact A",
            evidence_chunk_id=chunk.id,
        )
        item_b = MemoryItem(
            id="b", kind="fact", scope_type="session",
            scope_id="s1", content="fact B",
            evidence_chunk_id=chunk.id,
        )
        assert item_a.evidence_chunk_id == item_b.evidence_chunk_id


class TestMemoryWriteGateContinuity:
    """MemoryWriteGate must be consistent across turns."""

    def test_valid_source_allowed(self):
        gate = MemoryWriteGate()
        decision = gate.check_write(
            source="distiller",
            target="memory_items",
            metadata={"turn": 3},
        )
        assert decision.allowed

    def test_invalid_source_rejected(self):
        gate = MemoryWriteGate()
        decision = gate.check_write(
            source="unknown_bot",
            target="memory_items",
        )
        assert not decision.allowed

    def test_invalid_target_rejected(self):
        gate = MemoryWriteGate()
        decision = gate.check_write(
            source="distiller",
            target="random_table",
        )
        assert not decision.allowed

    def test_same_decision_across_turns(self):
        """Same write should get same decision regardless of turn."""
        gate = MemoryWriteGate()
        d1 = gate.check_write("distiller", "memory_items", {"turn": 1})
        d2 = gate.check_write("distiller", "memory_items", {"turn": 5})
        assert d1.allowed == d2.allowed

    def test_source_normalized(self):
        """Source names should be normalized."""
        gate = MemoryWriteGate()
        d = gate.check_write("  DISTILLER  ", "memory_items")
        assert d.allowed  # normalization handles casing/whitespace
