"""Autonomous memory maintenance — indexing, dedup, promotion (P3).

Runs during agent idle/autonomous mode. Does NOT use LLM for extraction.
All operations are deterministic: file scan, hash dedup, keyword match, time decay.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_line(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()[:16]


# ── Dedup helpers ─────────────────────────────────────────────────


def dedup_inbox(inbox_path: str | Path) -> dict:
    """Remove duplicate entries from the memory inbox. Returns {removed, kept, report}."""
    path = Path(inbox_path)
    if not path.is_file():
        return {"removed": 0, "kept": 0, "report": "inbox not found"}

    content = path.read_text(encoding="utf-8", errors="replace")
    entries = re.split(r"\n(?=## )", content)
    if len(entries) <= 1:
        return {"removed": 0, "kept": 1, "report": "single entry or empty"}

    seen: set[str] = set()
    unique: list[str] = []
    removed = 0

    for entry in entries:
        stripped = entry.strip()
        if not stripped:
            continue
        h = _hash_line(stripped[:200])
        if h in seen:
            removed += 1
        else:
            seen.add(h)
            unique.append(stripped)

    if removed > 0:
        path.write_text("\n\n".join(unique) + "\n", encoding="utf-8")

    return {"removed": removed, "kept": len(unique), "report": f"dedup: removed {removed} duplicates"}


# ── Time decay ────────────────────────────────────────────────────


def _entry_age_days(entry_text: str) -> int | None:
    """Extract Saved At date from an inbox entry."""
    m = re.search(r"Saved At:\s*(\d{4}-\d{2}-\d{2})", entry_text)
    if not m:
        return None
    try:
        saved = datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - saved).days
    except ValueError:
        return None


def score_inbox_entries(inbox_path: str | Path) -> list[dict]:
    """Score all inbox entries by recency + frequency signals. Returns sorted list."""
    path = Path(inbox_path)
    if not path.is_file():
        return []

    content = path.read_text(encoding="utf-8", errors="replace")
    entries = re.split(r"\n(?=## )", content)
    scores: list[dict] = []

    for entry in entries:
        stripped = entry.strip()
        if not stripped or not stripped.startswith("## "):
            continue

        age = _entry_age_days(stripped)
        question_count = len(re.findall(r"^\s*-\s+", stripped, re.MULTILINE))
        file_count = len(re.findall(r"Files Touched:", stripped))

        # Score: recency bonus + content richness
        score = 0.0
        if age is not None:
            score += max(0, 7 - age) * 1.0  # recent entries (≤7 days) get up to 7 points
        score += min(question_count, 5) * 0.5  # up to 2.5 points for questions
        score += min(file_count, 3) * 1.0  # up to 3 points for file touches

        scores.append({
            "title": stripped.split("\n")[0].replace("## ", "").strip()[:60],
            "age_days": age,
            "questions": question_count,
            "files_touched": file_count,
            "score": round(score, 1),
            "hash": _hash_line(stripped[:200]),
        })

    scores.sort(key=lambda s: s["score"], reverse=True)
    return scores


# ── Global memory context builder ──────────────────────────────────


def build_scoped_memory_context(
    user_query: str,
    max_chars: int = 3000,
) -> dict:
    """Build a scoped memory context block matching the query's keywords.
    Instead of injecting ALL of L1/L2, extract relevant sections by keyword match.
    Returns {context, source_files, matched_keywords, total_chars}.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    memory_dir = project_root / "memory"

    # Extract keywords from query
    query_lower = user_query.lower()
    keywords: list[str] = []
    # Chinese: split by common delimiters, filter short tokens
    for token in re.split(r"[，。！？、；：\s]+", user_query):
        token = token.strip()
        if len(token) >= 2:
            keywords.append(token)
    # Also keep the full query lowercased
    keywords.append(query_lower)

    context_parts: list[str] = []
    sources: list[str] = []

    for mem_file, label in [("global_mem_insight.txt", "L1"), ("global_mem.txt", "L2")]:
        path = memory_dir / mem_file
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        # Match: find paragraphs containing any keyword
        paragraphs = re.split(r"\n\n+", content)
        matched_paras = []
        for para in paragraphs:
            para_lower = para.lower()
            if any(kw.lower() in para_lower for kw in keywords):
                matched_paras.append(para.strip())
        if matched_paras:
            block = "\n\n".join(matched_paras)
            if len(block) > max_chars // 2:
                block = block[: max_chars // 2] + "\n... [truncated]"
            context_parts.append(f"[{label}] {path.name}:\n{block}")
            sources.append(str(path))

    context = "\n\n".join(context_parts)
    return {
        "context": context[:max_chars],
        "source_files": sources,
        "matched_keywords": [kw for kw in keywords if kw.lower() in context.lower()],
        "total_chars": len(context),
    }


# ── Maintenance orchestrator ──────────────────────────────────────


def run_memory_maintenance(project_root: str | Path | None = None) -> dict:
    """Run all deterministic memory maintenance tasks. Returns a report.
    Safe to call during autonomous idle mode — reads files, dedups inbox, builds scores.
    """
    root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent.parent
    memory_dir = root / "memory"
    inbox_path = memory_dir / "history_memory_inbox.md"

    report: dict[str, Any] = {
        "ran_at": _utc_now_iso(),
        "tasks": {},
    }

    # 1. Dedup inbox
    dedup_result = dedup_inbox(inbox_path)
    report["tasks"]["dedup"] = dedup_result

    # 2. Score inbox entries
    scores = score_inbox_entries(inbox_path)
    report["tasks"]["scored_entries"] = len(scores)
    report["tasks"]["top_entries"] = [
        {"title": s["title"], "score": s["score"], "age_days": s["age_days"]}
        for s in scores[:5]
    ]

    # 3. Check structured memory availability
    catalog_path = memory_dir / "catalog.sqlite"
    report["tasks"]["structured_memory_available"] = catalog_path.is_file()

    # 4. Quick stats on memory files
    for fname in ["global_mem_insight.txt", "global_mem.txt", "history_memory_inbox.md"]:
        fpath = memory_dir / fname
        if fpath.is_file():
            report["tasks"][f"size_{fname}"] = fpath.stat().st_size

    return report


# ── Standalone CLI ─────────────────────────────────────────────────


if __name__ == "__main__":
    import json
    report = run_memory_maintenance()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
