"""Rule-based tool schema selection for the classic executor."""

from __future__ import annotations

import os
import re
from typing import Any


SLIM_TOOLS_ENV_VAR = "GENERIC_AGENT_SLIM_TOOLS"


def slim_tools_enabled() -> bool:
    return str(os.environ.get(SLIM_TOOLS_ENV_VAR, "")).strip() == "1"


class ToolSchemaSelector:
    ALWAYS_INCLUDE = {"ask_user"}
    BASE_READ_ONLY = {"file_read", "ask_user"}
    FILE_DISCOVERY = {"file_read", "code_run", "ask_user"}
    WRITE_TOOLS = {"file_patch", "file_write"}
    WEB_TOOLS = {"web_scan", "web_execute_js"}
    MEMORY_HELPERS = {"update_working_checkpoint", "start_long_term_update"}
    MEMORY_QUERY_TOOLS = {"file_read", "code_run", "ask_user"}

    READ_PATTERNS = (
        r"readme",
        r"\bread\b",
        r"\btitle\b",
        r"\bfirst line\b",
        r"\blist\b",
        r"\bfind\b",
        r"\bsearch\b",
        r"\bgrep\b",
        r"\bproject\b",
        r"\bfile\b",
        r"读取",
        r"查看",
        r"第一行",
        r"标题",
        r"文件",
        r"目录",
        r"项目",
        r"查找",
        r"搜索",
        r"列出",
    )
    WRITE_PATTERNS = (
        r"\bmodify\b",
        r"\bedit\b",
        r"\bchange\b",
        r"\bpatch\b",
        r"\bwrite\b",
        r"\bupdate\b",
        r"\bcreate\b",
        r"\bimplement\b",
        r"\bfix\b",
        r"修改",
        r"编辑",
        r"更新",
        r"写入",
        r"新增",
        r"创建",
        r"实现",
        r"修复",
    )
    RUN_PATTERNS = (
        r"\brun\b",
        r"\btest\b",
        r"\bpytest\b",
        r"\binstall\b",
        r"\bstart\b",
        r"\bbuild\b",
        r"\bcompile\b",
        r"\bnpm\b",
        r"\bpip\b",
        r"\bshell\b",
        r"\bcommand\b",
        r"运行",
        r"测试",
        r"安装",
        r"启动",
        r"编译",
        r"命令",
        r"执行",
    )
    WEB_PATTERNS = (
        r"\bweb\b",
        r"\bbrowser\b",
        r"\bwebsite\b",
        r"\bsearch the web\b",
        r"网页",
        r"网站",
        r"浏览器",
        r"网页资料",
        r"上网",
    )
    MEMORY_PATTERNS = (
        r"\bmemory\b",
        r"\bhistory\b",
        r"\bprevious\b",
        r"\blast time\b",
        r"\brecall\b",
        r"记忆",
        r"历史",
        r"之前",
        r"上次",
        r"回忆",
    )
    COMPLEX_PATTERNS = (
        r"\bcomplex\b",
        r"\bend-to-end\b",
        r"\bmulti-step\b",
        r"\bwhole project\b",
        r"\bentire project\b",
        r"\brefactor\b",
        r"复杂",
        r"端到端",
        r"多步骤",
        r"整个项目",
        r"全量",
        r"全面",
        r"重构",
    )

    def select_tools_for_task(
        self,
        user_input: str,
        available_tools: list[dict[str, Any]],
        mode: str = "classic",
    ) -> list[dict[str, Any]]:
        if mode != "classic":
            return list(available_tools)

        names = [self._tool_name(tool) for tool in available_tools]
        tool_map = {name: tool for name, tool in zip(names, available_tools) if name}
        normalized = self._normalize(user_input)

        read_signal = self._matches(normalized, self.READ_PATTERNS)
        write_signal = self._matches(normalized, self.WRITE_PATTERNS)
        run_signal = self._matches(normalized, self.RUN_PATTERNS)
        web_signal = self._matches(normalized, self.WEB_PATTERNS)
        memory_signal = self._matches(normalized, self.MEMORY_PATTERNS)
        complex_signal = self._matches(normalized, self.COMPLEX_PATTERNS)
        signal_count = sum(bool(flag) for flag in (read_signal, write_signal, run_signal, web_signal, memory_signal))

        if complex_signal or signal_count >= 3:
            return list(available_tools)

        selected_names = set(self.ALWAYS_INCLUDE)

        if memory_signal:
            selected_names.update(self.MEMORY_QUERY_TOOLS)

        if web_signal:
            selected_names.update(self.WEB_TOOLS)
            selected_names.add("code_run")

        if write_signal:
            selected_names.update(self.FILE_DISCOVERY)
            selected_names.update(self.WRITE_TOOLS)
            selected_names.add("update_working_checkpoint")

        if run_signal:
            selected_names.update(self.FILE_DISCOVERY)
            selected_names.add("update_working_checkpoint")

        if read_signal:
            selected_names.update(self.FILE_DISCOVERY)

        if not selected_names or selected_names == self.ALWAYS_INCLUDE:
            selected_names.update(self.BASE_READ_ONLY)

        resolved = [tool_map[name] for name in names if name in selected_names and name in tool_map]
        if resolved:
            return resolved

        fallback_names = self.BASE_READ_ONLY if any(name in tool_map for name in self.BASE_READ_ONLY) else self.ALWAYS_INCLUDE
        return [tool_map[name] for name in names if name in fallback_names and name in tool_map]

    @staticmethod
    def _tool_name(tool: dict[str, Any]) -> str:
        if not isinstance(tool, dict):
            return ""
        function_part = tool.get("function")
        if isinstance(function_part, dict):
            return str(function_part.get("name") or "").strip()
        return str(tool.get("name") or "").strip()

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(str(text or "").lower().split())

    @staticmethod
    def _matches(text: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def select_tools_for_task(user_input: str, available_tools: list[dict[str, Any]], mode: str = "classic") -> list[dict[str, Any]]:
    return ToolSchemaSelector().select_tools_for_task(user_input, available_tools, mode=mode)
