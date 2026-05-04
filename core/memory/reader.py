"""Read-only memory adapter — wraps global memory + structured memory behind a single interface.

Does NOT change existing callers. Does NOT deprecate old memory sources.
Provides an optional structured search injection point for the OpenAI path.
"""

from __future__ import annotations

import os
from pathlib import Path

STRUCTURED_MEMORY_ENV_VAR = "GENERIC_AGENT_STRUCTURED_MEMORY"


def structured_memory_enabled() -> bool:
    return os.environ.get(STRUCTURED_MEMORY_ENV_VAR, "").strip() == "1"


def read_global_memory(project_root: str | Path | None = None) -> dict:
    """Read the legacy global memory text files. Returns {source, content, chars}."""
    root = Path(project_root) if project_root else _default_project_root()
    result: dict = {"global_mem_insight": None, "global_mem": None, "sources": [], "total_chars": 0}

    insight_path = root / "memory" / "global_mem_insight.txt"
    if insight_path.is_file():
        try:
            content = insight_path.read_text(encoding="utf-8", errors="replace")
            result["global_mem_insight"] = content
            result["sources"].append({"file": str(insight_path), "label": "L1", "chars": len(content)})
            result["total_chars"] += len(content)
        except Exception:
            pass

    mem_path = root / "memory" / "global_mem.txt"
    if mem_path.is_file():
        try:
            content = mem_path.read_text(encoding="utf-8", errors="replace")
            result["global_mem"] = content
            result["sources"].append({"file": str(mem_path), "label": "L2", "chars": len(content)})
            result["total_chars"] += len(content)
        except Exception:
            pass

    return result


def search_structured_memory(
    query: str,
    db_path: str | Path | None = None,
    limit: int = 5,
) -> dict:
    """Search the structured memory (SQLite FTS5) for relevant evidence chunks.
    Returns {results: [...], total_hits, error}.

    Requires GENERIC_AGENT_STRUCTURED_MEMORY=1 to produce results.
    """
    if not structured_memory_enabled():
        return {"results": [], "total_hits": 0, "error": None, "disabled": True}

    db = Path(db_path) if db_path else (_default_project_root() / "memory" / "catalog.sqlite")
    if not db.is_file():
        return {"results": [], "total_hits": 0, "error": "database not found", "disabled": False}

    try:
        from .store import MemoryStore

        store = MemoryStore(str(db))
        store.init_db()
        chunks = store.search_evidence_chunks(query, limit=limit)
        results = [
            {
                "source_path": c.source_path,
                "summary": c.summary,
                "content_preview": (c.content or "")[:500],
                "created_at": c.created_at,
            }
            for c in chunks
        ]
        return {"results": results, "total_hits": len(results), "error": None, "disabled": False}
    except Exception as e:
        return {"results": [], "total_hits": 0, "error": str(e), "disabled": False}


def read_working_memory(history: list[str], max_items: int = 20) -> str:
    """Format recent history as working memory (OpenAI path behavior).
    Does NOT change the existing _working_memory_message() — wraps the same logic.
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
    """Return a metadata report about which memory sources are active.
    Useful for profiler/audit records.
    """
    global_mem = read_global_memory()
    return {
        "l1_chars": sum(s["chars"] for s in global_mem["sources"] if s["label"] == "L1"),
        "l2_chars": sum(s["chars"] for s in global_mem["sources"] if s["label"] == "L2"),
        "structured_enabled": structured_memory_enabled(),
        "total_sources": len(global_mem["sources"]),
    }


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
