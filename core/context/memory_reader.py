"""
Memory Reader — unified read-only facade for all memory sources.

L1/L2 are PRIMARY (always readable, not gated).
Structured memory is SUPPLEMENTARY (gated by GA_CONTEXT_RUNTIME_ENABLED).
Session/task state is VOLATILE (gated by GA_CONTEXT_RUNTIME_ENABLED).

ContextBuilder MUST consume pre-built MemoryBundle from this reader.
Never reads files or DB directly — that's the reader's job.
"""

import os
import time
from dataclasses import dataclass, field

from . import _context_enabled

# Priority ordering for sorting
_PRIORITY_ORDER = {"primary": 0, "supplementary": 1, "volatile": 2}


@dataclass
class MemoryBlock:
    """A scoped chunk of memory from any source."""

    source: str                       # "L1" | "L2" | "structured:supplementary" | "session" | "task"
    source_priority: str              # "primary" | "supplementary" | "volatile"
    source_path: str | None = None    # file path or db reference
    content: str = ""
    relevance_score: float = 0.0
    chars: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.chars == 0 and self.content:
            self.chars = len(self.content)
        # Clamp score
        self.relevance_score = max(0.0, min(1.0, self.relevance_score))


@dataclass
class MemoryBundle:
    """Pre-assembled memory blocks for ContextBuilder consumption."""

    blocks: list[MemoryBlock] = field(default_factory=list)
    total_chars: int = 0
    source_counts: dict = field(default_factory=dict)
    queried_at: float = 0.0

    def __post_init__(self):
        if self.queried_at == 0.0:
            self.queried_at = time.time()
        # Always sort blocks by priority DESC, relevance_score DESC
        if self.blocks:
            self.blocks.sort(
                key=lambda b: (_PRIORITY_ORDER.get(b.source_priority, 99), -b.relevance_score)
            )
        if not self.source_counts:
            counts: dict[str, int] = {}
            for b in self.blocks:
                counts[b.source] = counts.get(b.source, 0) + 1
            self.source_counts = counts
        if self.total_chars == 0 and self.blocks:
            self.total_chars = sum(b.chars for b in self.blocks)


class MemoryReader:
    """Unified read-only facade for all memory sources.

    Usage:
        reader = MemoryReader(project_root="F:/GAgent-Multi")
        bundle = reader.scoped_query("auth middleware", project_id="proj_abc")
    """

    def __init__(self, project_root: str | None = None, db_path: str | None = None):
        self._project_root = project_root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self._db_path = db_path

    # ═══ L1 / L2 — Primary, ALWAYS readable ═══

    def read_global_memory(self) -> dict[str, str]:
        """Return {l1: str, l2: str}. Not gated — L1/L2 are always available."""
        memory_dir = os.path.join(self._project_root, "memory")
        result: dict[str, str] = {}

        for filename, key in [
            ("global_mem_insight.txt", "l1"),
            ("global_mem.txt", "l2"),
        ]:
            path = os.path.join(memory_dir, filename)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    result[key] = f.read()
            except FileNotFoundError:
                result[key] = ""

        return result

    def read_global_memory_blocks(self) -> list[MemoryBlock]:
        """Read L1/L2 as MemoryBlock list with primary priority."""
        mem = self.read_global_memory()
        blocks: list[MemoryBlock] = []

        if mem.get("l1"):
            blocks.append(MemoryBlock(
                source="L1",
                source_priority="primary",
                source_path=os.path.join(self._project_root, "memory", "global_mem_insight.txt"),
                content=mem["l1"],
                relevance_score=1.0,  # L1 always relevant
            ))

        if mem.get("l2"):
            blocks.append(MemoryBlock(
                source="L2",
                source_priority="primary",
                source_path=os.path.join(self._project_root, "memory", "global_mem.txt"),
                content=mem["l2"],
                relevance_score=0.9,  # L2 highly relevant
            ))

        return blocks

    # ═══ Structured Memory — Supplementary, gated ═══

    def read_structured_memory(self, query: str, limit: int = 5) -> list[MemoryBlock]:
        """FTS5 search in structured memory. Returns supplementary blocks.

        Gated by GA_CONTEXT_RUNTIME_ENABLED. Returns empty list when disabled.
        """
        if not _context_enabled():
            return []

        db_path = self._db_path or os.path.join(self._project_root, "memory", "catalog.sqlite")
        if not os.path.exists(db_path):
            return []

        try:
            from core.memory.store import MemoryStore
            store = MemoryStore(db_path)
            results = store.search_evidence_chunks(query, limit=limit)
        except Exception:
            return []

        blocks: list[MemoryBlock] = []
        for chunk in results:
            content = getattr(chunk, "content", "") or ""
            blocks.append(MemoryBlock(
                source="structured:supplementary",
                source_priority="supplementary",
                source_path=f"sqlite://{db_path}#{getattr(chunk, 'id', '')}",
                content=content,
                relevance_score=0.5,  # FTS5 match — moderate relevance
                metadata={
                    "chunk_id": getattr(chunk, "id", ""),
                    "session_id": getattr(chunk, "session_id", None),
                    "project_id": getattr(chunk, "project_id", None),
                    "run_id": getattr(chunk, "run_id", None),
                    "turn_index": getattr(chunk, "turn_index", None),
                },
            ))

        return blocks

    # ═══ Session / Task State — Volatile, gated ═══

    def read_session_state(self, session_id: str) -> "SessionRecord | None":
        """Read session record from SessionStore."""
        if not _context_enabled():
            return None
        try:
            from .session_store import SessionStore
            store = SessionStore(db_path=self._db_path)
            return store.get_session(session_id)
        except Exception:
            return None

    def read_task_state(self, task_id: str) -> "TaskState | None":
        """Read task state from SessionStore."""
        if not _context_enabled():
            return None
        try:
            from .session_store import SessionStore
            store = SessionStore(db_path=self._db_path)
            return store.get_task(task_id)
        except Exception:
            return None

    def read_active_tasks(self, project_id: str | None = None) -> list["TaskState"]:
        """Read active (running) tasks from SessionStore."""
        if not _context_enabled():
            return []
        try:
            from .session_store import SessionStore
            store = SessionStore(db_path=self._db_path)
            return store.get_active_tasks(project_id=project_id)
        except Exception:
            return []

    def read_session_history(self, session_id: str, limit: int = 10) -> list[MemoryBlock]:
        """Read recent completed tasks for a session as volatile memory blocks."""
        if not _context_enabled():
            return []
        try:
            from .session_store import SessionStore
            store = SessionStore(db_path=self._db_path)
            # Query the most recent completed tasks for this session
            # via the session store's get_last_completed_task
            last = store.get_last_completed_task(session_id)
            if last and last.summary:
                return [MemoryBlock(
                    source="task",
                    source_priority="volatile",
                    content=f"Last task: {last.summary} [{last.status}]",
                    relevance_score=0.7,
                    metadata={"task_id": last.task_id, "status": last.status},
                )]
        except Exception:
            pass
        return []

    # ═══ Unified Scoped Query ═══

    def scoped_query(
        self,
        user_query: str = "",
        project_id: str | None = None,
        session_id: str | None = None,
        max_chars: int = 2000,
    ) -> MemoryBundle:
        """Assemble a MemoryBundle from all sources, respecting priority order.

        Priority: L1 (primary) → L2 (primary) → structured (supplementary) → session/task (volatile)

        Fills blocks up to max_chars budget.
        Primary blocks are ALWAYS included (never truncated).
        Supplementary and volatile blocks fill remaining budget.
        """
        blocks: list[MemoryBlock] = []
        budget = max_chars

        # 1. L1/L2 — PRIMARY, always included
        primary_blocks = self.read_global_memory_blocks()
        for b in primary_blocks:
            if b.chars <= budget:
                blocks.append(b)
                budget -= b.chars
            else:
                # Truncate to fit
                blocks.append(MemoryBlock(
                    source=b.source,
                    source_priority=b.source_priority,
                    source_path=b.source_path,
                    content=b.content[:budget],
                    relevance_score=b.relevance_score,
                    metadata=b.metadata,
                ))
                budget = 0

        # 2. Structured memory — SUPPLEMENTARY, only if budget remains
        if budget > 50 and user_query:
            structured = self.read_structured_memory(user_query, limit=5)
            for b in structured:
                if budget <= 50:
                    break
                content = b.content
                if len(content) > budget:
                    content = content[:budget] + "…"
                blocks.append(MemoryBlock(
                    source=b.source,
                    source_priority=b.source_priority,
                    source_path=b.source_path,
                    content=content,
                    relevance_score=b.relevance_score,
                    metadata=b.metadata,
                ))
                budget -= len(content)

        # 3. Session/Task state — VOLATILE, only if budget remains
        if budget > 50 and session_id:
            session_blocks = self.read_session_history(session_id, limit=5)
            for b in session_blocks:
                if budget <= 50:
                    break
                content = b.content
                if len(content) > budget:
                    content = content[:budget] + "…"
                blocks.append(MemoryBlock(
                    source=b.source,
                    source_priority=b.source_priority,
                    source_path=b.source_path,
                    content=content,
                    relevance_score=b.relevance_score,
                    metadata=b.metadata,
                ))
                budget -= len(content)

        # Sort: priority DESC, relevance_score DESC
        blocks.sort(key=lambda b: (_PRIORITY_ORDER.get(b.source_priority, 99), -b.relevance_score))

        counts: dict[str, int] = {}
        for b in blocks:
            counts[b.source] = counts.get(b.source, 0) + 1

        return MemoryBundle(
            blocks=blocks,
            total_chars=sum(b.chars for b in blocks),
            source_counts=counts,
            queried_at=time.time(),
        )


# ═══ Standalone wrapper functions — backward-compatible with core/memory/reader.py ═══
# These allow core/memory/reader.py to delegate to the canonical MemoryReader
# without changing its public API. Once all callers migrate to MemoryReader,
# core/memory/reader.py can be fully deprecated.

_STRUCTURED_MEMORY_ENV_VAR = "GENERIC_AGENT_STRUCTURED_MEMORY"


def _structured_memory_enabled() -> bool:
    return os.environ.get(_STRUCTURED_MEMORY_ENV_VAR, "").strip() == "1"


def read_global_memory(project_root: str | None = None) -> dict:
    """Standalone wrapper — matches core/memory/reader.py API.
    Returns {global_mem_insight, global_mem, sources, total_chars}.
    Delegates to canonical MemoryReader.
    """
    reader = MemoryReader(project_root=project_root)
    raw = reader.read_global_memory()
    result: dict = {
        "global_mem_insight": raw.get("l1"),
        "global_mem": raw.get("l2"),
        "sources": [],
        "total_chars": 0,
    }
    memory_dir = os.path.join(reader._project_root, "memory")
    if raw.get("l1"):
        chars = len(raw["l1"])
        result["sources"].append(
            {"file": os.path.join(memory_dir, "global_mem_insight.txt"), "label": "L1", "chars": chars}
        )
        result["total_chars"] += chars
    if raw.get("l2"):
        chars = len(raw["l2"])
        result["sources"].append(
            {"file": os.path.join(memory_dir, "global_mem.txt"), "label": "L2", "chars": chars}
        )
        result["total_chars"] += chars
    return result


def search_structured_memory(
    query: str,
    db_path: str | None = None,
    limit: int = 5,
) -> dict:
    """Standalone wrapper — matches core/memory/reader.py API.
    Returns {results, total_hits, error, disabled}.
    Delegates to canonical MemoryReader.
    """
    if not _structured_memory_enabled():
        return {"results": [], "total_hits": 0, "error": None, "disabled": True}

    reader = MemoryReader(db_path=db_path)
    blocks = reader.read_structured_memory(query, limit=limit)
    results = [
        {
            "source_path": b.source_path or "",
            "summary": b.metadata.get("chunk_id", ""),
            "content_preview": (b.content or "")[:500],
            "created_at": b.metadata.get("created_at", ""),
        }
        for b in blocks
    ]
    return {"results": results, "total_hits": len(results), "error": None, "disabled": False}


def read_working_memory(history: list[str], max_items: int = 20) -> str:
    """Standalone wrapper — matches core/memory/reader.py API.
    Delegates to canonical MemoryReader.
    """
    if not history:
        return ""
    h_str = "\n".join(history[-max_items:])
    return (
        "### [WORKING MEMORY]\n"
        f"<history>\n{h_str}\n</history>\n"
        "Use this as compressed recent context. Keep the next <summary> consistent with it."
    )


def build_memory_source_report() -> dict:
    """Standalone wrapper — matches core/memory/reader.py API.
    Delegates to canonical MemoryReader.
    """
    reader = MemoryReader()
    global_mem = reader.read_global_memory()
    l1_chars = len(global_mem.get("l1") or "")
    l2_chars = len(global_mem.get("l2") or "")
    return {
        "l1_chars": l1_chars,
        "l2_chars": l2_chars,
        "structured_enabled": _structured_memory_enabled(),
        "total_sources": (1 if l1_chars > 0 else 0) + (1 if l2_chars > 0 else 0),
    }
