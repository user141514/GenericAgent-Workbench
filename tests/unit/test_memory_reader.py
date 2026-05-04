"""Phase 4: MemoryReader unit tests."""
import os
import time
import pytest
from core.context.memory_reader import MemoryReader, MemoryBlock, MemoryBundle


@pytest.fixture
def project_root():
    """Use the actual project root for L1/L2 reads."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def reader(project_root):
    return MemoryReader(project_root=project_root)


class TestReadGlobalMemory:
    """L1/L2 reads — always available, not gated by env var."""

    def test_read_global_memory_returns_l1_l2(self, reader):
        mem = reader.read_global_memory()
        assert "l1" in mem
        assert "l2" in mem
        assert len(mem["l1"]) > 0
        assert len(mem["l2"]) > 0

    def test_read_global_memory_blocks(self, reader):
        blocks = reader.read_global_memory_blocks()
        assert len(blocks) >= 1
        for b in blocks:
            assert b.source_priority == "primary"
            assert b.source in ("L1", "L2")
            assert b.relevance_score > 0.0

    def test_global_memory_readable_even_when_disabled(self, reader):
        """L1/L2 reads work regardless of env var."""
        saved = os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)
        try:
            mem = reader.read_global_memory()
            assert len(mem["l1"]) > 0  # still readable
        finally:
            if saved:
                os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = saved


class TestReadStructuredMemory:
    """Structured memory reads — gated, supplementary."""

    def test_read_structured_returns_supplementary(self, reader):
        os.environ["GA_CONTEXT_RUNTIME_ENABLED"] = "1"
        try:
            blocks = reader.read_structured_memory("python project")
            for b in blocks:
                assert b.source == "structured:supplementary"
                assert b.source_priority == "supplementary"
        finally:
            os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)

    def test_read_structured_empty_when_disabled(self, reader):
        os.environ.pop("GA_CONTEXT_RUNTIME_ENABLED", None)
        blocks = reader.read_structured_memory("anything")
        assert blocks == []


class TestMemoryBundle:
    """MemoryBundle dataclass invariants."""

    def test_bundle_sorted_by_priority_then_score(self):
        blocks = [
            MemoryBlock(source="task", source_priority="volatile", content="v1", relevance_score=0.9),
            MemoryBlock(source="L1", source_priority="primary", content="p1", relevance_score=0.5),
            MemoryBlock(source="structured:supplementary", source_priority="supplementary", content="s1", relevance_score=0.8),
            MemoryBlock(source="L2", source_priority="primary", content="p2", relevance_score=0.9),
        ]
        bundle = MemoryBundle(blocks=blocks)
        priorities = [b.source_priority for b in bundle.blocks]
        assert priorities == ["primary", "primary", "supplementary", "volatile"]

    def test_bundle_total_chars(self):
        blocks = [
            MemoryBlock(source="L1", source_priority="primary", content="hello"),
            MemoryBlock(source="L2", source_priority="primary", content="world"),
        ]
        bundle = MemoryBundle(blocks=blocks)
        assert bundle.total_chars == 10

    def test_bundle_source_counts(self):
        blocks = [
            MemoryBlock(source="L1", source_priority="primary", content="a"),
            MemoryBlock(source="L1", source_priority="primary", content="b"),
            MemoryBlock(source="L2", source_priority="primary", content="c"),
        ]
        bundle = MemoryBundle(blocks=blocks)
        assert bundle.source_counts.get("L1") == 2
        assert bundle.source_counts.get("L2") == 1

    def test_bundle_queried_at_recent(self):
        bundle = MemoryBundle(blocks=[])
        assert abs(bundle.queried_at - time.time()) < 2.0


class TestMemoryBlock:
    """MemoryBlock dataclass invariants."""

    def test_chars_auto_computed(self):
        b = MemoryBlock(source="L1", source_priority="primary", content="hello world")
        assert b.chars == 11

    def test_relevance_score_clamped(self):
        b1 = MemoryBlock(source="L1", source_priority="primary", content="x", relevance_score=1.5)
        assert b1.relevance_score == 1.0
        b2 = MemoryBlock(source="L1", source_priority="primary", content="x", relevance_score=-0.5)
        assert b2.relevance_score == 0.0

    def test_metadata_defaults_empty(self):
        b = MemoryBlock(source="L1", source_priority="primary", content="x")
        assert b.metadata == {}


class TestScopedQuery:
    """End-to-end scoped_query with project root."""

    def test_scoped_query_includes_primary(self, reader):
        bundle = reader.scoped_query("test", max_chars=2000)
        sources = {b.source for b in bundle.blocks}
        assert "L1" in sources or "L2" in sources

    def test_scoped_query_respects_max_chars(self, reader):
        bundle = reader.scoped_query("test", max_chars=200)
        assert bundle.total_chars <= 200
