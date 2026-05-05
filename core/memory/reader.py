"""Read-only memory adapter — DEPRECATED wrapper.

All functions delegate to the canonical MemoryReader at
core/context/memory_reader.py. This module is retained for backward
compatibility only. New code should use MemoryReader directly.

DEPRECATED: phase=M3, replaced_by=core.context.memory_reader.MemoryReader
"""

from __future__ import annotations

import os
from pathlib import Path

STRUCTURED_MEMORY_ENV_VAR = "GENERIC_AGENT_STRUCTURED_MEMORY"

_warned: set[str] = set()


def _deprecation_warning(func_name: str) -> None:
    """Emit a deprecation warning once per session per function."""
    if func_name in _warned:
        return
    _warned.add(func_name)
    import warnings
    warnings.warn(
        f"core.memory.reader.{func_name} is deprecated (phase=M3). "
        f"Use core.context.memory_reader.MemoryReader instead.",
        DeprecationWarning,
        stacklevel=3,
    )


def structured_memory_enabled() -> bool:
    return os.environ.get(STRUCTURED_MEMORY_ENV_VAR, "").strip() == "1"


def read_global_memory(project_root: str | Path | None = None) -> dict:
    """DEPRECATED. Delegates to canonical MemoryReader."""
    _deprecation_warning("read_global_memory")
    from core.context.memory_reader import read_global_memory as _canonical_read
    return _canonical_read(project_root=str(project_root) if project_root else None)


def search_structured_memory(
    query: str,
    db_path: str | Path | None = None,
    limit: int = 5,
) -> dict:
    """DEPRECATED. Delegates to canonical MemoryReader."""
    _deprecation_warning("search_structured_memory")
    from core.context.memory_reader import search_structured_memory as _canonical_search
    return _canonical_search(query=query, db_path=str(db_path) if db_path else None, limit=limit)


def read_working_memory(history: list[str], max_items: int = 20) -> str:
    """DEPRECATED. Delegates to canonical MemoryReader."""
    _deprecation_warning("read_working_memory")
    from core.context.memory_reader import read_working_memory as _canonical_wm
    return _canonical_wm(history=history, max_items=max_items)


def build_memory_source_report() -> dict:
    """DEPRECATED. Delegates to canonical MemoryReader."""
    _deprecation_warning("build_memory_source_report")
    from core.context.memory_reader import build_memory_source_report as _canonical_report
    return _canonical_report()


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
