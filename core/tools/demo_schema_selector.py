"""Minimal self-check for rule-based tool schema selection."""

from __future__ import annotations

import json
from pathlib import Path

from .schema_selector import ToolSchemaSelector


def _load_schema() -> list[dict]:
    path = Path("F:/GAgent-Multi/assets/tools_schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _names(selected: list[dict]) -> set[str]:
    result = set()
    for tool in selected:
        if isinstance(tool, dict):
            fn = tool.get("function") or {}
            result.add(str(fn.get("name") or tool.get("name") or ""))
    return result


def main() -> None:
    selector = ToolSchemaSelector()
    schema = _load_schema()

    read_names = _names(selector.select_tools_for_task("读取 README 第一行", schema))
    assert "file_read" in read_names
    assert "code_run" in read_names
    assert "file_write" not in read_names
    assert "web_scan" not in read_names

    run_names = _names(selector.select_tools_for_task("运行测试", schema))
    assert "code_run" in run_names
    assert "file_read" in run_names

    write_names = _names(selector.select_tools_for_task("修改 core/ga.py", schema))
    assert "file_read" in write_names
    assert "file_patch" in write_names or "file_write" in write_names

    web_names = _names(selector.select_tools_for_task("搜索网页资料", schema))
    assert "web_scan" in web_names
    assert "web_execute_js" in web_names

    memory_names = _names(selector.select_tools_for_task("回忆上次怎么修的", schema))
    assert "file_read" in memory_names
    assert "code_run" in memory_names

    minimal_names = _names(selector.select_tools_for_task("你好，简单聊聊吧", schema))
    assert minimal_names.issubset({"file_read", "ask_user"})
    assert "file_read" in minimal_names

    print("demo_schema_selector: OK")


if __name__ == "__main__":
    main()
