"""Structured memory ledger package."""

from .indexer import MemoryIndexer, chunk_text
from .maintenance import (
    archive_inbox_to_structured,
    build_scoped_memory_context,
    dedup_inbox,
    run_memory_maintenance,
    score_inbox_entries,
)
from .distillation import (
    build_distillation_candidate,
    format_inbox_entry,
    get_distillation_mode,
    trigger_distillation,
    write_distillation_candidate,
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
    "build_distillation_candidate",
    "build_legacy_memory_block",
    "format_inbox_entry",
    "get_distillation_mode",
    "read_legacy_l1_l2",
    "trigger_distillation",
    "write_distillation_candidate",
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
    "archive_inbox_to_structured",
    "build_scoped_memory_context",
    "dedup_inbox",
    "read_global_memory",
    "read_working_memory",
    "run_memory_maintenance",
    "score_inbox_entries",
    "search_structured_memory",
    "structured_memory_enabled",
]
