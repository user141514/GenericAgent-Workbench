"""
Session Dump / Restore — minimal working-memory persistence.

Saves a lightweight snapshot of the current session state so a new
session can recover awareness of an unfinished task. Does NOT store
full conversation content or sensitive data.

Dumps are written to temp/session_dumps/<session_id>.json.
Auto-cleaned after 7 days.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ══════════════════════════════════════════════════════════════════════
# Constants
# ══════════════════════════════════════════════════════════════════════

_SESSION_DUMP_DIR = "temp/session_dumps"
_MAX_AGE_DAYS = 7
_MAX_HISTORY_SUMMARY_CHARS = 2000
_MAX_KEY_INFO_CHARS = 1000
_MAX_TOOL_EVENTS = 20


# ══════════════════════════════════════════════════════════════════════
# Dump
# ══════════════════════════════════════════════════════════════════════

def dump_session(
    *,
    session_id: str,
    active_task: str = "",
    key_info: str = "",
    history_summary: str = "",
    pending_changes: list[str] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
    project_root: str | Path | None = None,
) -> str | None:
    """Save a minimal session snapshot to disk.

    Args:
        session_id: Unique session identifier.
        active_task: Description of the current active task.
        key_info: Key working memory facts (truncated).
        history_summary: Recent conversation summary (truncated).
        pending_changes: List of pending change descriptions.
        tool_events: Recent tool events [{name, status, summary}].
        project_root: Project root directory.

    Returns:
        Path to the dump file, or None on failure.
    """
    root = Path(project_root) if project_root else _default_root()
    dump_dir = root / _SESSION_DUMP_DIR
    dump_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)

    dump: dict[str, Any] = {
        "session_id": session_id,
        "dumped_at": now.isoformat(),
        "active_task": active_task[:500],
        "key_info": (key_info or "")[:_MAX_KEY_INFO_CHARS],
    }

    # History summary — condensed, no full conversation
    if history_summary:
        dump["history_summary"] = history_summary[:_MAX_HISTORY_SUMMARY_CHARS]

    # Pending changes — just descriptions, not full diffs
    if pending_changes:
        dump["pending_changes"] = [str(c)[:200] for c in pending_changes[:10]]

    # Tool events — name + status + short summary, no args
    if tool_events:
        dump["tool_events"] = []
        for te in tool_events[-_MAX_TOOL_EVENTS:]:
            dump["tool_events"].append({
                "name": str(te.get("name", ""))[:80],
                "status": str(te.get("status", "unknown"))[:20],
                "summary": str(te.get("summary", "") or "")[:200],
            })

    file_name = f"{session_id}.json"
    file_path = dump_dir / file_name
    try:
        file_path.write_text(
            json.dumps(dump, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return str(file_path)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════
# Restore
# ══════════════════════════════════════════════════════════════════════

def restore_session(
    session_id: str,
    project_root: str | Path | None = None,
) -> dict[str, Any] | None:
    """Restore a previously dumped session snapshot.

    Returns None if no dump exists or it's older than 7 days.
    """
    root = Path(project_root) if project_root else _default_root()
    file_path = root / _SESSION_DUMP_DIR / f"{session_id}.json"

    if not file_path.is_file():
        return None

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Age check
    dumped_at = data.get("dumped_at", "")
    if dumped_at:
        try:
            dump_time = datetime.fromisoformat(dumped_at)
            # Normalize to UTC if naive
            if dump_time.tzinfo is None:
                dump_time = dump_time.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - dump_time
            if age.days > _MAX_AGE_DAYS:
                # Auto-clean: remove expired dump
                try:
                    file_path.unlink()
                except Exception:
                    pass
                return None
        except ValueError:
            pass

    return data


# ══════════════════════════════════════════════════════════════════════
# List / cleanup
# ══════════════════════════════════════════════════════════════════════

def list_session_dumps(
    project_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """List all available session dumps with summary info."""
    root = Path(project_root) if project_root else _default_root()
    dump_dir = root / _SESSION_DUMP_DIR
    if not dump_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for f in sorted(dump_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            results.append({
                "session_id": data.get("session_id", f.stem),
                "dumped_at": data.get("dumped_at", ""),
                "active_task": (data.get("active_task") or "")[:120],
                "has_pending_changes": bool(data.get("pending_changes")),
                "tool_event_count": len(data.get("tool_events") or []),
            })
        except Exception:
            continue
    return results


def cleanup_expired_dumps(
    project_root: str | Path | None = None,
) -> int:
    """Remove session dumps older than _MAX_AGE_DAYS. Returns count removed."""
    root = Path(project_root) if project_root else _default_root()
    dump_dir = root / _SESSION_DUMP_DIR
    if not dump_dir.is_dir():
        return 0

    removed = 0
    cutoff = time.time() - (_MAX_AGE_DAYS * 86400)
    for f in dump_dir.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            continue
    return removed


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
