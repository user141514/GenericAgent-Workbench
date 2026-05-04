"""Structured memory ledger package."""

from .indexer import MemoryIndexer, chunk_text
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
    "read_global_memory",
    "read_working_memory",
    "search_structured_memory",
    "structured_memory_enabled",
]
