"""Phase M1 tests for stapp_memory_panel module."""

import os
import tempfile

import pytest


class TestGetMemoryContent:
    """get_memory_content() reads memory files from project root."""

    def test_empty_when_no_memory_dir(self, tmp_path):
        from frontends.stapp_memory_panel import get_memory_content
        result = get_memory_content(str(tmp_path))
        assert result == {}

    def test_reads_existing_files(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "global_mem_insight.txt").write_text("L1 content", encoding="utf-8")
        (mem_dir / "global_mem.txt").write_text("L2 content", encoding="utf-8")

        from frontends.stapp_memory_panel import get_memory_content
        result = get_memory_content(str(tmp_path))
        assert result["global_mem_insight.txt"] == "L1 content"
        assert result["global_mem.txt"] == "L2 content"
        assert "history_memory_inbox.md" not in result  # doesn't exist

    def test_inbox_file_when_present(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "history_memory_inbox.md").write_text("inbox content", encoding="utf-8")

        from frontends.stapp_memory_panel import get_memory_content
        result = get_memory_content(str(tmp_path))
        assert result["history_memory_inbox.md"] == "inbox content"


class TestModuleNoSessionState:
    """Module must not reference st.session_state or agent."""

    def test_no_session_state_access(self):
        import inspect
        from frontends.stapp_memory_panel import render_memory_panel, get_memory_content
        r_source = inspect.getsource(render_memory_panel)
        g_source = inspect.getsource(get_memory_content)
        assert "st.session_state" not in r_source
        assert "st.session_state" not in g_source

    def test_no_agent_access(self):
        import inspect
        from frontends.stapp_memory_panel import render_memory_panel, get_memory_content
        source = inspect.getsource(render_memory_panel) + inspect.getsource(get_memory_content)
        assert "agent." not in source
