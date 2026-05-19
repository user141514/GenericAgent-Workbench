"""History restore service — decouples history file discovery/parsing from Streamlit UI.

Receives file paths and backend kind, delegates to ``chatapp_common.py`` for
the actual ``format_restore`` / ``unpack_restore_result`` parsing, and returns
plain dataclass results.  Does NOT depend on Streamlit, ``st.session_state``,
or agent objects.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class HistoryFileInfo:
    """Metadata for a single history file.  Streamlit-free."""

    filepath: str
    filename: str
    mtime: float = 0.0
    mtime_str: str = ""
    size_kb: int = 0
    title: str = ""


@dataclass
class RestoredConversation:
    """Result of restoring a conversation from a history file.

    ``restored`` is the raw data: a list of input_items (new format)
    or a list of lines (old format).  ``fmt_type`` is ``"input_items"``
    or ``"lines"``.
    """

    restored: list[Any] = field(default_factory=list)
    count: int = 0
    fmt_type: str = "lines"
    filename: str = ""


class HistoryRestoreService:
    """Stateless service for history file operations.

    No Streamlit, no ``st.session_state``, no agent mutations.
    All heavy parsing delegates to ``chatapp_common`` helpers.
    """

    # ── file discovery ──────────────────────────────────────────────────

    @staticmethod
    def _history_dir(backend_kind: str = "") -> str:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        subdir = "model_responses_openai" if backend_kind == "openai-agents" else "model_responses"
        return os.path.join(script_dir, "..", "temp", subdir)

    def list_files(self, backend_kind: str = "") -> list[HistoryFileInfo]:
        """List available history files, newest first."""
        hist_dir = self._history_dir(backend_kind)
        if not os.path.exists(hist_dir):
            return []
        files = glob.glob(os.path.join(hist_dir, "model_responses_*.txt"))
        files.sort(key=os.path.getmtime, reverse=True)
        results: list[HistoryFileInfo] = []
        for filepath in files[:20]:
            fname = os.path.basename(filepath)
            mtime = os.path.getmtime(filepath)
            size_kb = max(1, os.path.getsize(filepath) // 1024)
            info = HistoryFileInfo(
                filepath=filepath,
                filename=fname,
                mtime=mtime,
                mtime_str=datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M"),
                size_kb=size_kb,
            )
            results.append(info)
        return results

    # ── preview ─────────────────────────────────────────────────────────

    @staticmethod
    def preview(filepath: str, max_lines: int = 30) -> str:
        """Read the first *max_lines* lines of a history file."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return "\n".join(f.read().splitlines()[:max_lines])
        except Exception as e:
            return f"预览失败: {e}"

    # ── title extraction ────────────────────────────────────────────────

    def extract_title(self, filepath: str, backend_kind: str = "") -> str:
        """Extract the last user question from a history file for display."""
        from frontends.chatapp_common import format_restore, _content_to_text, unpack_restore_result

        result, err = format_restore(filepath, backend_kind=backend_kind)
        if err or not result:
            return ""
        restored, _, _, fmt_type = unpack_restore_result(result)
        questions: list[str] = []
        if fmt_type == "input_items":
            for item in restored or []:
                if not isinstance(item, dict) or item.get("role") != "user":
                    continue
                text = _content_to_text(item.get("content", ""))
                text = text.strip()
                if text:
                    questions.append(text)
        else:
            questions = [
                line[8:] for line in restored
                if isinstance(line, str) and line.startswith("[USER]: ")
            ]
        if questions:
            title = questions[-1].replace("\n", " ").strip()
            return title[:42] + ("..." if len(title) > 42 else "")
        return ""

    # ── restore ─────────────────────────────────────────────────────────

    def restore(
        self, filepath: str, backend_kind: str = ""
    ) -> RestoredConversation | None:
        """Parse a history file and return a ``RestoredConversation``.

        Returns None if the file cannot be parsed.
        The caller (stapp.py) is responsible for injecting the result into
        ``st.session_state.messages`` and ``agent.history``.
        """
        from frontends.chatapp_common import format_restore, unpack_restore_result

        result, err = format_restore(filepath, backend_kind=backend_kind)
        if err or not result:
            return None
        restored, _, count, fmt_type = unpack_restore_result(result)
        return RestoredConversation(
            restored=restored or [],
            count=count,
            fmt_type=fmt_type or "lines",
            filename=os.path.basename(filepath),
        )
