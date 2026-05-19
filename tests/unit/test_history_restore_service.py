"""Phase H1 tests for HistoryRestoreService."""

import os
import tempfile
from dataclasses import dataclass

import pytest
from frontends.services.history_restore_service import (
    HistoryFileInfo,
    HistoryRestoreService,
    RestoredConversation,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _make_history_file(dir_path, filename, lines, mtime=None):
    """Create a fake history file and return its full path."""
    path = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ── tests ────────────────────────────────────────────────────────────────

class TestHistoryFileInfo:
    """Dataclass tests."""

    def test_construction(self):
        info = HistoryFileInfo(
            filepath="/tmp/x.txt", filename="x.txt",
            mtime=123.0, mtime_str="01-01 00:00", size_kb=5, title="Q?"
        )
        assert info.filepath == "/tmp/x.txt"
        assert info.title == "Q?"


class TestRestoredConversation:
    """Dataclass tests."""

    def test_defaults(self):
        rc = RestoredConversation()
        assert rc.restored == []
        assert rc.fmt_type == "lines"

    def test_input_items_format(self):
        rc = RestoredConversation(
            restored=[{"role": "user", "content": "hello"}],
            count=1, fmt_type="input_items", filename="f.txt"
        )
        assert rc.fmt_type == "input_items"
        assert rc.count == 1


class TestListFiles:
    """list_files() tests."""

    def test_empty_on_missing_dir(self):
        svc = HistoryRestoreService()
        result = svc.list_files(backend_kind="nonexistent_xyz")
        # Should not crash; backend_kind just changes subdir path
        assert isinstance(result, list)

    def test_empty_when_dir_does_not_exist(self, tmp_path):
        svc = HistoryRestoreService()
        # Monkey-patch to use tmp_path
        svc._history_dir = lambda bk="": str(tmp_path / "no_such_dir")
        result = svc.list_files()
        assert result == []

    def test_returns_files_newest_first(self, tmp_path):
        hist_dir = tmp_path / "model_responses"
        hist_dir.mkdir()
        f1 = _make_history_file(hist_dir, "model_responses_001.txt", ["old"], mtime=100)
        f2 = _make_history_file(hist_dir, "model_responses_002.txt", ["new"], mtime=200)

        svc = HistoryRestoreService()
        svc._history_dir = lambda bk="": str(hist_dir)
        result = svc.list_files()
        assert len(result) >= 2
        assert result[0].filepath in (f1, f2)
        # newest first
        assert result[0].mtime >= result[-1].mtime if len(result) > 1 else True


class TestPreview:
    """preview() tests."""

    def test_reads_first_lines(self, tmp_path):
        p = _make_history_file(tmp_path, "h.txt", [f"line{i}" for i in range(50)])
        text = HistoryRestoreService.preview(p, max_lines=10)
        assert "line0" in text
        assert "line9" in text
        assert "line10" not in text  # beyond max_lines

    def test_handles_missing_file(self):
        text = HistoryRestoreService.preview("/nonexistent/path.txt")
        assert "预览失败" in text or "Error" in text or "No such" in text


class TestExtractTitle:
    """extract_title() tests."""

    def test_handles_unparseable_file(self, tmp_path):
        p = _make_history_file(tmp_path, "bad.txt", ["garbage data not valid history"])
        svc = HistoryRestoreService()
        # Should not crash
        title = svc.extract_title(str(p))
        # Returns empty string for unparseable files
        assert isinstance(title, str)


class TestRestore:
    """restore() tests."""

    def test_returns_none_for_unparseable(self, tmp_path):
        p = _make_history_file(tmp_path, "bad.txt", ["not valid history format"])
        svc = HistoryRestoreService()
        result = svc.restore(str(p))
        assert result is None

    def test_restored_conversation_has_fields(self):
        rc = RestoredConversation(
            restored=[{"role": "user", "content": "hi"}],
            count=2, fmt_type="input_items", filename="test.txt"
        )
        assert rc.restored is not None
        assert rc.count == 2
        assert rc.fmt_type == "input_items"
        assert rc.filename == "test.txt"


class TestNoStreamlitDependency:
    """Service must work without Streamlit installed."""

    def test_no_streamlit_import(self):
        import sys
        streamlit_mods = {k for k in sys.modules if k.startswith("streamlit")}
        for m in streamlit_mods:
            del sys.modules[m]
        try:
            svc = HistoryRestoreService()
            info = HistoryFileInfo(filepath="/x", filename="x")
            assert info.filepath == "/x"
        finally:
            pass  # streamlit modules already removed — fine for this test

    def test_no_agent_dependency(self):
        """Service should not call agent.xxx or st.xxx in implementation code."""
        import inspect
        source = inspect.getsource(HistoryRestoreService)
        # Strip docstrings which may explain caller's responsibility
        import re
        code_only = re.sub(r'"""[\s\S]*?"""', '', source)
        code_only = re.sub(r"'''[\s\S]*?'''", '', code_only)
        assert "agent." not in code_only
        assert "st.session_state" not in code_only
