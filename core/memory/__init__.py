"""Structured memory ledger package."""

from .indexer import MemoryIndexer, chunk_text
from .maintenance import (
    build_scoped_memory_context,
    dedup_inbox,
    run_memory_maintenance,
    score_inbox_entries,
)
from .legacy_global import build_legacy_memory_block, read_legacy_l1_l2
from .reader import (
    STRUCTURED_MEMORY_ENV_VAR,
    build_memory_source_report,
    read_global_memory,
    read_working_memory,
    search_structured_memory,
    structured_memory_enabled,
)
from .store import MemoryStore
from .types import EvidenceChunk, MemoryCandidate, MemoryEvent, MemoryItem
from .write_gate import (
    MemoryWriteDecision,
    MemoryWriteGate,
    MemoryWriteSource,
    MemoryWriteTarget,
)

__all__ = [
    "build_legacy_memory_block",
    "read_legacy_l1_l2",
    "MemoryStore",
    "MemoryIndexer",
    "chunk_text",
    "MemoryItem",
    "MemoryCandidate",
    "EvidenceChunk",
    "MemoryEvent",
    "MemoryWriteGate",
    "MemoryWriteDecision",
    "MemoryWriteSource",
    "MemoryWriteTarget",
    "STRUCTURED_MEMORY_ENV_VAR",
    "build_memory_source_report",
    "build_scoped_memory_context",
    "dedup_inbox",
    "read_global_memory",
    "read_working_memory",
    "run_memory_maintenance",
    "score_inbox_entries",
    "search_structured_memory",
    "structured_memory_enabled",
]
