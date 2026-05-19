"""Integration test: memory persistence pipeline (P2-5).

Tests the full chain: reader → store → search → context,
without requiring real LLM calls.
"""

import os
import tempfile
from pathlib import Path

import pytest

from core.context.memory_reader import (
    build_memory_source_report,
    read_global_memory,
    read_working_memory,
    search_structured_memory,
    structured_memory_enabled,
)
from core.memory.store import MemoryStore
from core.memory.write_gate import MemoryWriteGate, MemoryWriteDecision
from core.memory.indexer import MemoryIndexer, chunk_text


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_catalog.sqlite"
    store = MemoryStore(str(db_path))
    store.init_db()
    return store


class TestMemoryPersistencePipeline:
    """Write → Index → Search → Read pipeline."""

    def test_write_evidence_chunk(self, temp_db):
        chunk = temp_db.add_evidence_chunk(
            source_path="test/file.py",
            content="def hello(): return 'world'",
            source="manual_user",
            source_type="text_file",
        )
        assert chunk.id is not None

    def test_write_and_read_memory_item(self, temp_db):
        item = temp_db.add_memory_item(
            kind="fact",
            scope_type="project",
            scope_id="test-project",
            content="Python 3.11 is the target version",
            source="distiller",
        )
        assert item.id is not None

        retrieved = temp_db.get_memory_item(item.id)
        assert retrieved is not None
        assert retrieved.content == "Python 3.11 is the target version"

    def test_write_gate_blocks_agent_durable_write(self, temp_db):
        with pytest.raises(PermissionError, match="Memory write denied"):
            temp_db.add_memory_item(
                kind="fact",
                scope_type="project",
                scope_id="test",
                content="should be blocked",
                source="agent",  # "agent" is NOT in DURABLE_SOURCES
            )

    def test_write_gate_allows_distiller(self, temp_db):
        item = temp_db.add_memory_item(
            kind="fact",
            scope_type="project",
            scope_id="test",
            content="distiller can write",
            source="distiller",
        )
        assert item.id is not None

    def test_indexer_chunks_text(self):
        text = "Line 1\n\nLine 2\n\nLine 3\n\nLine 4"
        chunks = chunk_text(text, chunk_size=12, chunk_overlap=3)
        assert len(chunks) >= 2

    def test_gate_standalone(self):
        gate = MemoryWriteGate()
        decision = gate.check_write(source="agent", target="memory_items")
        assert decision.allowed is False
        assert decision.required_redirect == "memory_candidates"

        decision2 = gate.check_write(source="distiller", target="memory_items")
        assert decision2.allowed is True


class TestReaderPipeline:
    """Reader → source report → working memory pipeline."""

    def test_read_global_memory_has_expected_keys(self):
        result = read_global_memory()
        assert "global_mem_insight" in result
        assert "global_mem" in result
        assert "sources" in result
        assert "total_chars" in result

    def test_working_memory_with_data(self):
        history = ["user: 你好", "assistant: 你好！有什么可以帮你的？"]
        wm = read_working_memory(history, max_items=10)
        assert "[WORKING MEMORY]" in wm
        assert "你好" in wm

    def test_reader_report_consistent(self):
        report1 = build_memory_source_report()
        report2 = build_memory_source_report()
        # Report should be consistent between calls
        assert report1["total_sources"] == report2["total_sources"]

    def test_structured_search_disabled_by_default(self):
        assert structured_memory_enabled() is False
        result = search_structured_memory("test")
        assert result["disabled"] is True
        assert result["results"] == []
