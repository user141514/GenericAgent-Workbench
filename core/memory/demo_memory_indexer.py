"""Minimal self-check for the raw history memory indexer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.memory import MemoryIndexer, MemoryStore


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "memory_indexer.sqlite3"
        docs_dir = root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        md_path = docs_dir / "restore_note.md"
        md_path.write_text(
            "User: restore bug happened because report_id route was broken\n\n"
            "Assistant: the restore flow depends on a valid route.",
            encoding="utf-8",
        )
        txt_path = docs_dir / "history.txt"
        txt_path.write_text(
            "User: another small note about indexing history files.",
            encoding="utf-8",
        )

        store = MemoryStore(db_path)
        store.init_db()
        indexer = MemoryIndexer(store)

        ids = indexer.index_file(md_path, project_id="demo-project")
        assert ids, "expected index_file to return chunk ids"

        hits = store.search_evidence_chunks("restore bug", project_id="demo-project")
        assert hits, "expected search to find restore bug chunk"

        again = indexer.index_file(md_path, project_id="demo-project")
        assert len(again) == len(ids), "re-index should resolve to the same number of chunks"

        dir_ids = indexer.index_directory(docs_dir, project_id="demo-project")
        assert dir_ids, "expected index_directory to return chunk ids"

        print("demo_memory_indexer: OK")


if __name__ == "__main__":
    main()
