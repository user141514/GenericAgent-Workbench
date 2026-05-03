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
        "读取", "读文件", "写文件", "修改文件", "删除文件",
        "创建文件", "打开文件", "保存文件", "文件内容", "查看文件",
        "文件", "目录",
        # Code execution and environment work.
        "运行", "执行", "运行代码", "执行代码", "跑一个", "试运行",
        "pip", "安装", "卸载", "import",
        # Browser / web tasks.
        "浏览", "网页", "网站", "搜索", "查找",
        "打开链接", "点击", "输入", "填写", "提交",
        # System operations.
        "命令", "终端", "shell", "bash", "cmd", "powershell",
        "进程", "服务", "启动", "停止", "重启",
        # Development workflow.
        "git", "commit", "push", "pull", "clone", "merge",
        "调试", "测试", "build", "编译",
        # Planning / validation intents.
        "规划", "拆解", "任务拆分", "分阶段", "方案", "roadmap",
        "pytest", "单测", "验证", "怎么验证", "验收标准", "自检", "回归",
        # Strong action verbs.
        "帮我", "请", "把", "将", "给", "让", "做",
        # ── Cross-cutting triggers (ensure sub-category queries reach executor gate) ──
        # Code triggers (multi-word specific signals)
        "写一个", "写代码", "编写", "重构", "重写", "添加", "增加",
        "加一个", "改代码", "改成", "实现一个", "实现", "修改", "改一下",
        # Review triggers
        "审查", "review", "检查", "修复", "fix", "bug", "排查", "自查",
        "找bug", "找问题", "代码规范", "有没有", "是否安全",
        # Research triggers
        "查一下", "查查", "找一下", "找找", "怎么用", "如何使用",
        "文档", "API", "是什么原因", "报错", "日志", "调研", "技术选型",
    ]

    # ── Fine-grained sub-classification keywords (Level 1 refinement) ──

    CODE_KEYWORDS = [
        # Code writing / modification.
        "写一个", "写代码", "编写", "实现一个", "添加一个",
        "加一个", "加功能", "修改代码", "改代码", "重构", "重写",
        "创建类", "新建", "生成代码", "实现功能", "开发",
        "写段", "写个", "帮我写", "写函数", "写方法", "写接口",
        "写模块", "代码实现", "编程",
        # More code variants (multi-word only to avoid noise)
        "改成", "改一下", "修改", "添加", "实现", "增加功能",
        "优化代码", "改进代码", "完善代码",
        "提取方法", "封装成", "抽象出",
        "算法实现", "数据结构", "设计模式", "单例模式", "工厂模式",
        "异步处理", "多线程", "装饰器模式", "上下文管理器",
        "加一个类", "继承关系",
    ]

    REVIEW_KEYWORDS = [
        # Code review / testing / verification.
        "审查", "review", "review代码", "检查代码", "代码审查",
        "代码检查", "找bug", "bug", "找问题", "漏洞", "安全审查", "安全审计",
        "内存泄漏", "性能问题", "性能优化",
        "测试用例", "单元测试", "集成测试",
        "修复测试", "修测试", "修复bug", "修bug",
        "fix", "修复", "修一下", "修了",
        "排查", "定位问题", "自查", "检查一下", "检查错误",
        "质量检查", "lint", "代码规范", "代码风格",
        # More review variants
        "检查", "看一下", "有没有", "是否存在", "是否安全",
        "线程安全", "并发安全", "SQL注入", "XSS", "CSRF",
        "注入", "越权", "权限", "异常处理", "错误处理",
        "测试覆盖", "覆盖率", "性能测试", "压力测试",
        "安全", "审计", "评审", "验收",
    ]

    RESEARCH_KEYWORDS = [
        # Information gathering / documentation / exploration.
        "搜索一下", "查一下", "查查", "找一下", "找找",
        "文档", "官方文档", "API文档", "API",
        "怎么用", "如何使用", "使用方法", "用法",
        "了解", "知道", "讲一下", "讲一讲",
        "解释一下", "说明一下",
        "错误信息", "报错信息", "日志分析", "查看日志", "看看日志",
        "阅读代码", "翻阅文档",
        "调研", "技术选型", "对比方案", "技术方案",
        "方案对比", "技术调研", "调研一下", "调查",
        # More research variants (multi-word preferred, single words only if strong)
        "查找", "找到", "搜索",
        "是什么原因", "什么原因", "怎么回事",
        "用法示例", "示例代码", "代码例子",
        "官方文档", "版本更新", "新特性", "更新日志", "changelog",
        "参考资料", "教程", "怎么配置",
        "配置文件", "环境变量",
        "看看文档", "查看文档", "看一下文档",
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
        "介绍一个", "介绍一下",
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
        (r"^/(code|run|write|read|search|browse|open|exec)", "executor"),
        (r"^/(review|test|check|verify)", "review"),
        (r"^/(research|find|lookup|explore)", "research"),
        (r"^/(chat|ask|explain)", "chat"),
    ]

    EXCLUDE_PATTERNS = [
        r"只是.*问一[下个]",
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

    # Pre-compiled regex patterns (built once at class-load time).
    _EXCLUDE_RES = [re.compile(p) for p in EXCLUDE_PATTERNS]  # type: ignore[name-defined]
    _COMMAND_RES = [(re.compile(p), t) for p, t in COMMAND_PATTERNS]  # type: ignore[name-defined]

    @classmethod
    def match(cls, query: str) -> RouteResult:
        if not query or not query.strip():
            return RouteResult(target=None)

        query = query.strip()
        query_lower = query.lower()

        # Pre-compiled exclude pattern check
        for pattern in cls._EXCLUDE_RES:
            if pattern.search(query):
                return RouteResult(target=None, matched_rule="excluded")

        # Pre-compiled command pattern check
        for pattern, target in cls._COMMAND_RES:
            if pattern.match(query_lower):
                return RouteResult(
                    target=target,
                    matched_rule=f"command:{pattern.pattern}",
                    confidence=1.0,
                )

        # Single-pass keyword scan: count hits for all categories at once.
        executor_hits = 0
        chat_hits = 0
        code_hits = 0
        review_hits = 0
        research_hits = 0

        for kw in cls.EXECUTOR_KEYWORDS:
            if kw in query:
                executor_hits += 1
        for kw in cls.CHAT_KEYWORDS:
            if kw in query:
                chat_hits += 1
        for kw in cls.CODE_KEYWORDS:
            if kw in query:
                code_hits += 1
        for kw in cls.REVIEW_KEYWORDS:
            if kw in query:
                review_hits += 1
        for kw in cls.RESEARCH_KEYWORDS:
            if kw in query:
                research_hits += 1

        executor_score = executor_hits * 1.5
        chat_score = chat_hits * 1.0

        for verb in cls.ACTION_START_VERBS:
            if query.startswith(verb):
                target = cls._pick_subtype(code_hits, review_hits, research_hits, fallback="executor")
                return RouteResult(
                    target=target,
                    matched_rule=f"action_start:{verb}->{target}",
                    confidence=0.95,
                )

        if executor_score > chat_score and executor_hits > 0:
            target = cls._pick_subtype(code_hits, review_hits, research_hits, fallback="executor")
            return RouteResult(
                target=target,
                matched_rule=f"keywords:{target}({executor_hits}e/{chat_hits}c)",
                confidence=min(0.9, 0.5 + executor_hits * 0.08),
            )

        if chat_score > executor_score and chat_hits > 0:
            return RouteResult(
                target="chat",
                matched_rule=f"keywords:chat({chat_hits})",
                confidence=min(0.9, 0.6 + chat_hits * 0.1),
            )

        return RouteResult(target=None, matched_rule="no_match")

    @staticmethod
    def _pick_subtype(code: int, review: int, research: int, fallback: str = "executor") -> str:
        """Pick the best sub-type from pre-computed hit counts (no extra scan)."""
        scores = {"code": code, "review": review, "research": research}
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_target, best_score = sorted_scores[0]
        second_score = sorted_scores[1][1]

        if best_score >= 2 and best_score >= second_score + 1:
            return best_target
        if best_score == 1 and second_score == 0:
            return best_target
        return fallback

    # ── Parallel sub-task detection (Level 3 advancement) ──────────

    # Connectors that suggest independent parallel sub-tasks.
    _PARALLEL_CONNECTORS = [
        "同时", "并且同时", "与此同时",
        "一方面", "另一方面",
    ]

    @classmethod
    def try_parallel_split(cls, query: str) -> list[str] | None:
        """Detect parallelizable multi-intent queries and split into sub-tasks.

        Returns a list of sub-queries or None if the query is not parallelizable.
        Each sub-query must be independently executable.
        """
        query = query.strip()
        if not query:
            return None

        # Try connector-based split first
        for connector in cls._PARALLEL_CONNECTORS:
            if connector in query:
                parts = [p.strip() for p in query.split(connector) if p.strip()]
                if len(parts) >= 2 and all(len(p) >= 4 for p in parts):
                    return parts

        # Try "和" as a connector (ambiguous — only split when both sides have action verbs)
        if "和" in query:
            parts = query.split("和")
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()
                # Both sides must contain action keywords to be parallel tasks
                left_action = any(kw in left for kw in cls.EXECUTOR_KEYWORDS)
                right_action = any(kw in right for kw in cls.EXECUTOR_KEYWORDS)
                if left_action and right_action and len(left) >= 4 and len(right) >= 4:
                    return [left, right]

        return None

    @classmethod
    def get_stats(cls) -> dict:
        return {
            "executor_keywords": len(cls.EXECUTOR_KEYWORDS),
            "chat_keywords": len(cls.CHAT_KEYWORDS),
            "code_keywords": len(cls.CODE_KEYWORDS),
            "review_keywords": len(cls.REVIEW_KEYWORDS),
            "research_keywords": len(cls.RESEARCH_KEYWORDS),
            "command_patterns": len(cls.COMMAND_PATTERNS),
            "exclude_patterns": len(cls.EXCLUDE_PATTERNS),
        }


def quick_route(query: str) -> Optional[str]:
    return RouterRules.match(query).target


class RouterStats:
    """Runtime stats for quick router hits (including fine-grained targets)."""

    _stats = {
        "total_queries": 0,
        "chat_hits": 0,
        "executor_hits": 0,
        "code_hits": 0,
        "review_hits": 0,
        "research_hits": 0,
        "no_match": 0,
        "rule_breakdown": {},
        "unmatched_queries": [],
    }
    _max_unmatched_samples = 100

    @classmethod
    def record(cls, result: RouteResult, query: str = "") -> None:
        cls._stats["total_queries"] += 1

        target = result.target
        if target == "chat":
            cls._stats["chat_hits"] += 1
        elif target == "executor":
            cls._stats["executor_hits"] += 1
        elif target == "code":
            cls._stats["code_hits"] += 1
        elif target == "review":
            cls._stats["review_hits"] += 1
        elif target == "research":
            cls._stats["research_hits"] += 1
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

        def pct(count):
            return f"{count / total * 100:.1f}%" if total > 0 else "0.0%"

        return {
            "total_queries": total,
            "hit_rate": pct(
                cls._stats["chat_hits"]
                + cls._stats["executor_hits"]
                + cls._stats["code_hits"]
                + cls._stats["review_hits"]
                + cls._stats["research_hits"]
            ),
            "chat_rate": pct(cls._stats["chat_hits"]),
            "executor_rate": pct(cls._stats["executor_hits"]),
            "code_rate": pct(cls._stats["code_hits"]),
            "review_rate": pct(cls._stats["review_hits"]),
            "research_rate": pct(cls._stats["research_hits"]),
            "no_match_rate": pct(cls._stats["no_match"]),
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
            "code_hits": 0,
            "review_hits": 0,
            "research_hits": 0,
            "no_match": 0,
            "rule_breakdown": {},
            "unmatched_queries": [],
        }
