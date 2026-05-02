"""Minimal self-check for the structured memory store."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.memory import MemoryStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "memory_store.sqlite3"
        store = MemoryStore(db_path)
        store.init_db()

        evidence = store.add_evidence_chunk(
            source_path="temp/model_responses/demo.txt",
            source_type="model_response",
            actor="assistant",
            source="agent",
            content="restore bug happened because report_id route was broken",
            project_id="demo-project",
            session_id="demo-session",
        )
        hits = store.search_evidence_chunks(
            "restore bug",
            limit=10,
            project_id="demo-project",
        )
        assert hits, "expected at least one evidence search result"
        assert any(hit.id == evidence.id for hit in hits), "expected to find the inserted evidence chunk"

        item = store.add_memory_item(
            kind="decision",
            scope_type="project",
            scope_id="demo-project",
            content="The restore flow depends on a valid report_id route.",
            source="distiller",
            summary="restore flow requires report_id route",
            evidence_chunk_id=evidence.id,
            verified=1,
            confidence=0.9,
        )
        loaded = store.get_memory_item(item.id)
        assert loaded is not None, "expected to load inserted memory item"
        assert loaded.id == item.id, "loaded memory item id mismatch"
        assert loaded.content == item.content, "loaded memory item content mismatch"

        print("demo_memory_store: OK")


if __name__ == "__main__":
    main()
