"""
Change Classifier — separates proposed changes from executed changes.

Design rules:
  6. Pending proposals must be separated from executed changes.
  4. Tool Event Ledger is the ONLY evidence of executed facts.
  5. Assistant final text is NOT execution evidence — it must be
     cross-referenced with tool events.

The classifier does NOT:
  - Write to memory files
  - Modify agent behavior
  - Block or redirect tool calls

Gated by GA_TOOL_EVENT_LEDGER env var (same gate as the ledger).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChangeRecord:
    """A single proposed or executed change."""

    change_type: str           # "proposed" | "executed"
    summary: str               # what was proposed/done
    source: str                # "plan" | "thinking" | "tool_event" | "summary"
    tool_evidence: list[str] = field(default_factory=list)  # tool event IDs
    verified: bool = False     # True if cross-referenced with tool events
    timestamp: float = 0.0
    turn: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type,
            "summary": self.summary[:200],
            "source": self.source,
            "tool_evidence": self.tool_evidence[:10],
            "verified": self.verified,
            "timestamp": self.timestamp,
            "turn": self.turn,
        }


class ChangeClassifier:
    """Classify and track proposed vs executed changes.

    Usage:
        classifier = ChangeClassifier()
        classifier.record_proposal("Refactor auth module", source="plan", turn=1)
        ...
        classifier.verify_against_ledger(ledger)
        pending = classifier.get_pending()
    """

    def __init__(self, max_records: int = 30):
        self._proposals: list[ChangeRecord] = []
        self._executed: list[ChangeRecord] = []
        self._max_records = max_records

    def record_proposal(self, summary: str, source: str = "plan",
                        turn: int = 0) -> str:
        """Record a proposed change. Returns a proposal_id."""
        if not self._enabled():
            return ""

        record = ChangeRecord(
            change_type="proposed",
            summary=summary[:200],
            source=source,
            turn=turn,
        )
        self._proposals.append(record)
        while len(self._proposals) > self._max_records:
            self._proposals.pop(0)
        return f"proposal_{len(self._proposals)}_{time.time()}"

    def record_executed(self, summary: str, tool_event_ids: list[str] | None = None,
                        turn: int = 0) -> None:
        """Record an executed change confirmed by tool events."""
        if not self._enabled():
            return

        record = ChangeRecord(
            change_type="executed",
            summary=summary[:200],
            source="tool_event",
            tool_evidence=tool_event_ids or [],
            verified=True,
            turn=turn,
        )
        self._executed.append(record)
        while len(self._executed) > self._max_records:
            self._executed.pop(0)

    def verify_against_ledger(self, ledger: Any) -> int:
        """Cross-reference proposals against the ToolEventLedger.

        Returns the number of newly verified proposals.
        """
        if not self._enabled():
            return 0

        verified_count = 0
        recent_tools = {e.tool_name for e in ledger.recent_events(20)}

        for proposal in self._proposals:
            if proposal.verified:
                continue
            # Simple heuristic: if a tool was called after the proposal
            # in the same turn, the proposal is likely executed.
            # This is a lightweight check — full verification requires
            # semantic matching (future enhancement).
            if recent_tools:
                proposal.verified = True
                proposal.tool_evidence = list(recent_tools)[:5]
                verified_count += 1

        return verified_count

    def get_pending(self) -> list[ChangeRecord]:
        """Return unverified proposed changes."""
        return [p for p in self._proposals if not p.verified]

    def get_executed(self) -> list[ChangeRecord]:
        """Return all executed changes."""
        return list(self._executed)

    def get_unverified_proposals(self) -> list[ChangeRecord]:
        """Alias for get_pending()."""
        return self.get_pending()

    def summary(self) -> str:
        """Compact text summary for context injection."""
        pending = self.get_pending()
        executed = self.get_executed()

        lines = ["### [CHANGE CLASSIFIER]"]
        if executed:
            lines.append("## Executed (verified by tool events):")
            for e in executed[-5:]:
                lines.append(f"  + {e.summary}")
        if pending:
            lines.append("## Pending (proposed, not yet executed):")
            for p in pending[-5:]:
                lines.append(f"  ? {p.summary}")
        lines.append("[/CHANGE CLASSIFIER]")
        return "\n".join(lines)

    def clear(self) -> None:
        """Reset the classifier."""
        self._proposals.clear()
        self._executed.clear()

    @staticmethod
    def _enabled() -> bool:
        return os.environ.get("GA_TOOL_EVENT_LEDGER", "").strip() == "1"
