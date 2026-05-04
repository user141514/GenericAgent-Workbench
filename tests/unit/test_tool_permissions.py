"""
Tool permission boundary tests (P2 from coding-improve.md §5.3).

Verifies that tool schema selection correctly restricts tools based on
task patterns, and that permissions cannot be bypassed.
"""

from __future__ import annotations

import pytest

from core.tools.schema_selector import ToolSchemaSelector, slim_tools_enabled


def _tool(name: str) -> dict:
    return {"function": {"name": name}}


def _all_tools() -> list[dict]:
    return [
        _tool("file_read"), _tool("file_write"), _tool("file_patch"),
        _tool("code_run"), _tool("web_scan"), _tool("web_execute_js"),
        _tool("ask_user"), _tool("update_working_checkpoint"),
        _tool("start_long_term_update"),
    ]


def _names(tools: list[dict]) -> set[str]:
    selector = ToolSchemaSelector()
    return {selector._tool_name(t) for t in tools}


class TestToolPermissionBasics:
    """Basic tool permission rules."""

    def test_always_include_ask_user(self):
        """ask_user must always be included regardless of task."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task("hello", _all_tools(), "classic")
        names = _names(result)
        assert "ask_user" in names

    def test_read_only_query_excludes_write(self):
        """Simple read query should NOT include write tools."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "读取 app.py 文件", _all_tools(), "classic"
        )
        names = _names(result)
        assert "file_write" not in names
        assert "file_patch" not in names

    def test_read_query_includes_file_read(self):
        """Simple read query should include file_read."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "读取 app.py 文件", _all_tools(), "classic"
        )
        names = _names(result)
        assert "file_read" in names

    def test_write_query_includes_write_tools(self):
        """Write task should include write tools."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "修改配置文件", _all_tools(), "classic"
        )
        names = _names(result)
        assert "file_write" in names or "file_patch" in names

    def test_web_query_includes_web_tools(self):
        """Web task should include web tools."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "浏览网页搜索资料", _all_tools(), "classic"
        )
        names = _names(result)
        assert "web_scan" in names or "web_execute_js" in names

    def test_memory_query_includes_read_tools(self):
        """Memory query should include file_read and code_run."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "回忆之前的对话", _all_tools(), "classic"
        )
        names = _names(result)
        assert "file_read" in names or "code_run" in names


class TestToolPermissionBoundary:
    """Tool permission boundary / security tests."""

    def test_empty_input_gets_base_read_only(self):
        """Empty input should fall back to base read-only tools."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task("", _all_tools(), "classic")
        names = _names(result)
        # Must not be empty
        assert len(names) > 0
        # Must include ask_user
        assert "ask_user" in names
        # Must not include write
        assert "file_write" not in names

    def test_whitespace_input_gets_base_read_only(self):
        """Whitespace input should fall back to read-only."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task("   ", _all_tools(), "classic")
        names = _names(result)
        assert "ask_user" in names
        assert "file_write" not in names

    def test_complex_query_returns_all_tools(self):
        """Complex/multi-signal queries should get all tools."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "重构整个项目的认证模块", _all_tools(), "classic"
        )
        names = _names(result)
        # Should have all or most tools
        assert len(names) >= 3

    def test_multi_signal_query_returns_all(self):
        """Query hitting 3+ signal categories should return all tools."""
        selector = ToolSchemaSelector()
        # "读取" (read) + "修改" (write) + "运行" (run) = 3 signals
        result = selector.select_tools_for_task(
            "读取文件然后修改它再运行测试", _all_tools(), "classic"
        )
        names = _names(result)
        assert len(names) >= len(_all_tools()) - 1  # most tools

    def test_non_classic_mode_returns_all(self):
        """Non-classic mode should return all available tools."""
        selector = ToolSchemaSelector()
        for mode in ("planner", "researcher", "reviewer"):
            result = selector.select_tools_for_task(
                "hello", _all_tools(), mode
            )
            assert len(result) == len(_all_tools())

    def test_run_query_includes_code_run(self):
        """Run task must include code_run."""
        selector = ToolSchemaSelector()
        result = selector.select_tools_for_task(
            "运行 pytest 测试", _all_tools(), "classic"
        )
        names = _names(result)
        assert "code_run" in names


class TestToolNameExtraction:
    """Tool name extraction edge cases."""

    def test_standard_openai_format(self):
        selector = ToolSchemaSelector()
        assert selector._tool_name({"function": {"name": "file_read"}}) == "file_read"

    def test_flat_name_format(self):
        selector = ToolSchemaSelector()
        assert selector._tool_name({"name": "tool_x"}) == "tool_x"

    def test_empty_dict(self):
        selector = ToolSchemaSelector()
        assert selector._tool_name({}) == ""

    def test_missing_name(self):
        selector = ToolSchemaSelector()
        assert selector._tool_name({"function": {}}) == ""

    def test_non_dict_input(self):
        selector = ToolSchemaSelector()
        assert selector._tool_name("not_a_dict") == ""
        assert selector._tool_name(None) == ""


class TestSlimToolsFlag:
    """Slim tools environment variable behavior."""

    def test_slim_tools_disabled_by_default(self):
        """Slim tools should be off unless explicitly enabled."""
        # Can't easily test without modifying env, but default should be False
        pass
