"""Self-check for memory write gating."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.memory import MemoryStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "memory_write_gate.sqlite3"
        store = MemoryStore(db_path)
        store.init_db()

        try:
            store.add_memory_item(
                kind="fact",
                scope_type="project",
                scope_id="demo",
                content="skills may not write durable memory directly",
                source="skill",
            )
            raise AssertionError("skill write to memory_items should have been denied")
        except PermissionError as exc:
            message = str(exc)
            assert "required_redirect='memory_candidates'" in message, message

        candidate = store.add_memory_candidate(
            source="skill",
            source_id="activation-demo",
            kind="fact",
            scope_type="project",
            scope_id="demo",
            content="candidate memory from a skill",
            reason="should stay pending",
        )
        assert candidate.source == "skill", candidate
        assert candidate.status == "pending", candidate

        evidence = store.add_evidence_chunk(
            source="agent",
            source_path="temp/demo_evidence.txt",
            content="restore bug happened because report_id route was broken",
            source_type="demo",
            actor="assistant",
        )
        assert evidence.id, evidence

        distiller_item = store.add_memory_item(
            kind="decision",
            scope_type="project",
            scope_id="demo",
            content="distiller may write durable memory",
            source="distiller",
            evidence_chunk_id=evidence.id,
        )
        assert distiller_item.id, distiller_item

        try:
            store.add_memory_item(
                kind="fact",
                scope_type="project",
                scope_id="demo",
                content="unknown source should be denied for durable memory",
                source="unknown",
            )
            raise AssertionError("unknown write to memory_items should have been denied")
        except PermissionError:
            pass

        manual_item = store.add_memory_item(
            kind="fact",
            scope_type="project",
            scope_id="demo",
            content="manual user may write durable memory",
            source="manual_user",
        )
        assert manual_item.id, manual_item

        event = store.add_memory_event(
            source="skill",
            event_type="candidate_emitted",
            payload={"candidate_id": candidate.id},
        )
        assert event.id, event

        hits = store.search_evidence_chunks("restore bug")
        assert hits, "expected evidence search to keep working"

        print("demo_write_gate: OK")


if __name__ == "__main__":
    main()
