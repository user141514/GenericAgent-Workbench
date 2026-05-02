"""
Fast keyword-based router rules used before the LLM routing pass.

The goal is to short-circuit obvious chat-vs-executor requests with cheap
string matching while keeping the fallback path available for ambiguous cases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class RouteResult:
    target: str | None  # "chat" / "executor" / None
    matched_rule: str = ""
    confidence: float = 1.0


class RouterRules:
    """Rule-based quick router."""

    EXECUTOR_KEYWORDS = [
        # File operations.
        "读取",
        "读文件",
        "写文件",
        "修改文件",
        "删除文件",
        "创建文件",
        "打开文件",
        "保存文件",
        "文件内容",
        "查看文件",
        # Code execution and environment work.
        "运行",
        "执行",
        "运行代码",
        "执行代码",
        "跑一个",
        "试运行",
        "pip",
        "安装",
        "卸载",
        "import",
        # Browser / web tasks.
        "浏览",
        "网页",
        "网站",
        "搜索",
        "查找",
        "打开链接",
        "点击",
        "输入",
        "填写",
        "提交",
        # System operations.
        "命令",
        "终端",
        "shell",
        "bash",
        "cmd",
        "powershell",
        "进程",
        "服务",
        "启动",
        "停止",
        "重启",
        # Development workflow.
        "git",
        "commit",
        "push",
        "pull",
        "clone",
        "merge",
        "调试",
        "测试",
        "build",
        "编译",
        # Planning / validation intents that should reach planner.
        "规划",
        "拆解",
        "任务拆分",
        "分阶段",
        "方案",
        "roadmap",
        "pytest",
        "单测",
        "验证",
        "怎么验证",
        "验收标准",
        "自检",
        "回归",
        # Strong action verbs.
        "帮我",
        "请",
        "把",
        "将",
        "给",
        "让",
        "做",
    ]

    CHAT_KEYWORDS = [
        # Greetings.
        "你好",
        "您好",
        "早上好",
        "晚上好",
        "hi",
        "hello",
        "hey",
        # Thanks.
        "谢谢",
        "感谢",
        "thanks",
        "thank you",
        # Explanations and opinions.
        "是什么",
        "什么是",
        "为什么",
        "怎么理解",
        "如何理解",
        "解释一个",
        "说明一个",
        "介绍一个",
        "讲一个",
        "你觉得",
        "你认为",
        "怎么看",
        "怎么看待",
        "有什么区别",
        "有什么相同",
        "比较一个",
        "优点",
        "缺点",
        "好处",
        "坏处",
        # General question endings.
        "吗？",
        "呢？",
        "如何？",
        "怎样？",
    ]

    COMMAND_PATTERNS = [
        (r"^/(run|read|write|search|browse|open|exec)", "executor"),
        (r"^/(chat|ask|explain)", "chat"),
    ]

    EXCLUDE_PATTERNS = [
        r"只是.*问一个",
        r"想(了解|知道)",
        r"能不能|可不可以",
    ]

    ACTION_START_VERBS = [
        "帮我",
        "请",
        "把",
        "将",
        "给",
        "让",
        "读取",
        "运行",
        "执行",
        "搜索",
        "浏览",
        "写",
        "改",
        "删",
        "创建",
        "打开",
        "规划",
        "拆解",
        "验证",
    ]

    @classmethod
    def match(cls, query: str) -> RouteResult:
        if not query or not query.strip():
            return RouteResult(target=None)

        query = query.strip()
        query_lower = query.lower()

        for pattern in cls.EXCLUDE_PATTERNS:
            if re.search(pattern, query):
                return RouteResult(target=None, matched_rule="excluded")

        for pattern, target in cls.COMMAND_PATTERNS:
            if re.match(pattern, query_lower):
                return RouteResult(target=target, matched_rule=f"command:{pattern}", confidence=1.0)

        executor_hits = sum(1 for kw in cls.EXECUTOR_KEYWORDS if kw in query)
        chat_hits = sum(1 for kw in cls.CHAT_KEYWORDS if kw in query)

        executor_score = executor_hits * 1.5
        chat_score = chat_hits * 1.0

        for verb in cls.ACTION_START_VERBS:
            if query.startswith(verb):
                return RouteResult(
                    target="executor",
                    matched_rule=f"action_start:{verb}",
                    confidence=0.95,
                )

        if executor_score > chat_score and executor_hits > 0:
            return RouteResult(
                target="executor",
                matched_rule=f"keywords:executor({executor_hits})",
                confidence=min(0.9, 0.6 + executor_hits * 0.1),
            )

        if chat_score > executor_score and chat_hits > 0:
            return RouteResult(
                target="chat",
                matched_rule=f"keywords:chat({chat_hits})",
                confidence=min(0.9, 0.6 + chat_hits * 0.1),
            )

        return RouteResult(target=None, matched_rule="no_match")

    @classmethod
    def get_stats(cls) -> dict:
        return {
            "executor_keywords": len(cls.EXECUTOR_KEYWORDS),
            "chat_keywords": len(cls.CHAT_KEYWORDS),
            "command_patterns": len(cls.COMMAND_PATTERNS),
            "exclude_patterns": len(cls.EXCLUDE_PATTERNS),
        }


def quick_route(query: str) -> Optional[str]:
    return RouterRules.match(query).target


class RouterStats:
    """Runtime stats for quick router hits."""

    _stats = {
        "total_queries": 0,
        "chat_hits": 0,
        "executor_hits": 0,
        "no_match": 0,
        "rule_breakdown": {},
        "unmatched_queries": [],
    }
    _max_unmatched_samples = 100

    @classmethod
    def record(cls, result: RouteResult, query: str = "") -> None:
        cls._stats["total_queries"] += 1

        if result.target == "chat":
            cls._stats["chat_hits"] += 1
        elif result.target == "executor":
            cls._stats["executor_hits"] += 1
        else:
            cls._stats["no_match"] += 1
            if query and len(cls._stats["unmatched_queries"]) < cls._max_unmatched_samples:
                cls._stats["unmatched_queries"].append(query[:100])

        if result.matched_rule:
            cls._stats["rule_breakdown"][result.matched_rule] = (
                cls._stats["rule_breakdown"].get(result.matched_rule, 0) + 1
            )

    @classmethod
    def get_stats(cls) -> dict:
        total = cls._stats["total_queries"]
        if total == 0:
            return {"message": "暂无统计数据"}

        return {
            "total_queries": total,
            "hit_rate": f"{(cls._stats['chat_hits'] + cls._stats['executor_hits']) / total * 100:.1f}%",
            "chat_rate": f"{cls._stats['chat_hits'] / total * 100:.1f}%",
            "executor_rate": f"{cls._stats['executor_hits'] / total * 100:.1f}%",
            "no_match_rate": f"{cls._stats['no_match'] / total * 100:.1f}%",
            "top_rules": sorted(
                cls._stats["rule_breakdown"].items(),
                key=lambda item: item[1],
                reverse=True,
            )[:10],
            "unmatched_samples": cls._stats["unmatched_queries"][-10:],
        }

    @classmethod
    def reset(cls) -> None:
        cls._stats = {
            "total_queries": 0,
            "chat_hits": 0,
            "executor_hits": 0,
            "no_match": 0,
            "rule_breakdown": {},
            "unmatched_queries": [],
        }
