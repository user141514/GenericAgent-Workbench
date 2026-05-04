"""
Benchmark queries for multi-agent quality evaluation.

Each query has:
- text: the user input
- category: expected routing (code/review/research/chat)
- expected_agents: agents that should be involved in the pipeline
- evaluation_criteria: how to judge response quality
- difficulty: simple / medium / complex
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchmarkQuery:
    id: str
    text: str
    category: str  # code / review / research / chat / multi
    expected_agents: list[str] = field(default_factory=list)
    evaluation_criteria: list[str] = field(default_factory=list)
    difficulty: str = "simple"
    min_handoffs: int = 0  # minimum expected handoffs in pipeline


BENCHMARK_QUERIES = [
    # ── Code Queries ──
    BenchmarkQuery(
        id="code-01",
        text="帮我写一个 Python 的 LRU 缓存装饰器",
        category="code",
        expected_agents=["code_agent"],
        evaluation_criteria=[
            "代码语法正确可运行",
            "包含 LRU 缓存的完整实现",
            "有基本的错误处理",
        ],
        difficulty="simple",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="code-02",
        text="写一个 Flask REST API，包含用户注册和登录接口",
        category="code",
        expected_agents=["code_agent", "review_agent"],
        evaluation_criteria=[
            "包含完整的 REST API 代码",
            "有注册和登录两个端点",
            "有基本的输入验证",
            "经过 review 的代码质量更高",
        ],
        difficulty="medium",
        min_handoffs=2,  # code → review → code
    ),
    BenchmarkQuery(
        id="code-03",
        text="重构这个文件把同步调用改成 async/await",
        category="code",
        expected_agents=["code_agent", "review_agent"],
        evaluation_criteria=[
            "正确识别了需要改的调用",
            "async/await 使用正确",
            "没有破坏现有功能",
        ],
        difficulty="medium",
        min_handoffs=1,
    ),

    # ── Review Queries ──
    BenchmarkQuery(
        id="review-01",
        text="帮我审查这段代码的安全性，特别是 SQL 注入和 XSS 风险",
        category="review",
        expected_agents=["review_agent"],
        evaluation_criteria=[
            "检查了 SQL 注入风险",
            "检查了 XSS 风险",
            "给出了具体的修复建议",
            "引用了具体的代码行",
        ],
        difficulty="medium",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="review-02",
        text="review 一下这个 PR 的代码质量，重点关注性能问题",
        category="review",
        expected_agents=["review_agent"],
        evaluation_criteria=[
            "检查了性能问题",
            "给出了具体的优化建议",
            "区分了 critical/warning/suggestion",
        ],
        difficulty="medium",
        min_handoffs=0,
    ),

    # ── Research Queries ──
    BenchmarkQuery(
        id="research-01",
        text="搜索一下 Django 5.0 相比 4.2 有哪些新特性",
        category="research",
        expected_agents=["research_agent"],
        evaluation_criteria=[
            "列出了具体的新特性",
            "有对比说明",
            "引用了信息来源",
        ],
        difficulty="simple",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="research-02",
        text="帮我查查 FastAPI 的依赖注入怎么用，然后写一个示例",
        category="multi",
        expected_agents=["research_agent", "code_agent"],
        evaluation_criteria=[
            "先给出了 FastAPI 依赖注入的说明",
            "然后给出了可运行的代码示例",
            "agent 之间正确协作（research → code）",
        ],
        difficulty="medium",
        min_handoffs=1,
    ),

    # ── Multi-Step / Pipeline Queries ──
    BenchmarkQuery(
        id="multi-01",
        text="帮我写一个用户认证模块，然后检查它的安全性",
        category="multi",
        expected_agents=["code_agent", "review_agent"],
        evaluation_criteria=[
            "先产出了认证模块代码",
            "然后对其进行了安全性审查",
            "审查发现了具体问题或确认了安全性",
            "code→review 流程完整",
        ],
        difficulty="complex",
        min_handoffs=2,
    ),
    BenchmarkQuery(
        id="multi-02",
        text="查一下 JWT 的最佳实践，然后帮我实现一个 JWT 认证，再审查一下代码",
        category="multi",
        expected_agents=["research_agent", "code_agent", "review_agent"],
        evaluation_criteria=[
            "research_agent 给出了 JWT 最佳实践",
            "code_agent 基于研究结果实现了代码",
            "review_agent 审查了代码安全性",
            "research→code→review 流程完整",
        ],
        difficulty="complex",
        min_handoffs=2,
    ),

    # ── Chat Queries (control group) ──
    BenchmarkQuery(
        id="chat-01",
        text="什么是 Python 的 GIL？",
        category="chat",
        expected_agents=["chat_specialist"],
        evaluation_criteria=["回答准确", "解释清晰"],
        difficulty="simple",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="chat-02",
        text="你好，介绍一下你自己能做什么",
        category="chat",
        expected_agents=["chat_specialist"],
        evaluation_criteria=["描述了系统能力", "没有虚构操作"],
        difficulty="simple",
        min_handoffs=0,
    ),

    # ── Boundary / Edge Case Queries (P1 from coding-improve.md §5.3) ──
    # Note: empty/whitespace/unicode-safety tests live in tests/unit/test_idempotency.py
    BenchmarkQuery(
        id="boundary-04",
        text="帮我写代码 " * 100,
        category="code",
        expected_agents=["code_agent"],
        evaluation_criteria=["不应因输入过长而崩溃", "正确路由到 code_agent"],
        difficulty="simple",
        min_handoffs=0,
    ),
]

# Boundary queries that test crash-safety rather than routing accuracy.
# These are verified in tests/unit/test_idempotency.py, not by eval_runner.
BOUNDARY_QUERIES = [
    BenchmarkQuery(
        id="boundary-01",
        text="",
        category="chat",
        expected_agents=["chat_specialist"],
        evaluation_criteria=["不应崩溃或异常", "优雅处理空输入"],
        difficulty="simple",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="boundary-02",
        text="   ",
        category="chat",
        expected_agents=["chat_specialist"],
        evaluation_criteria=["不应崩溃", "优雅处理纯空格输入"],
        difficulty="simple",
        min_handoffs=0,
    ),
    BenchmarkQuery(
        id="boundary-03",
        text="emoji test 🚀🔥💻 中文混合 こんにちは",
        category="chat",
        expected_agents=["chat_specialist"],
        evaluation_criteria=["正确处理 unicode/emoji/多语言混合输入"],
        difficulty="simple",
        min_handoffs=0,
    ),
]
