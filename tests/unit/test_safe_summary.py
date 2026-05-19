from __future__ import annotations

from types import SimpleNamespace

from core.ga import GenericAgentHandler


def _handler() -> GenericAgentHandler:
    parent = SimpleNamespace(verbose=False)
    handler = GenericAgentHandler(parent, last_history=[], cwd="./temp")
    handler._last_user_input = "检查 core/router_rules.py 里的路由问题"
    return handler


def test_safe_summary_replaces_low_signal_summary_with_tool_fact():
    handler = _handler()
    response = SimpleNamespace(content="<summary>继续处理</summary>")
    tool_calls = [{"tool_name": "file_read", "args": {"path": "core/router_rules.py", "keyword": "match"}}]
    tool_results = [{"tool_use_id": "1", "content": "1| class RouterRules\n198| def match(cls, query: str) -> RouteResult:"}]

    summary, fallback_used = handler._safe_summary(response, tool_calls, tool_results, turn=1)

    assert fallback_used is True
    assert "router_rules.py" in summary
    assert "继续处理" not in summary
    assert "调用工具" not in summary


def test_safe_summary_rejects_hallucinated_user_clarification():
    handler = _handler()
    response = SimpleNamespace(content="<summary>用户澄清了认证范围，准备继续</summary>")
    tool_calls = [{"tool_name": "code_run", "args": {"script": "pytest -q", "type": "powershell"}}]
    tool_results = [{"tool_use_id": "1", "content": "2 passed, 1 failed"}]

    summary, fallback_used = handler._safe_summary(response, tool_calls, tool_results, turn=1)

    assert fallback_used is True
    assert "1 failed" in summary or "1失败" in summary


def test_safe_summary_keeps_grounded_summary():
    handler = _handler()
    response = SimpleNamespace(content="<summary>已读取 core/router_rules.py，准备调整匹配规则</summary>")
    tool_calls = [{"tool_name": "file_read", "args": {"path": "core/router_rules.py"}}]
    tool_results = [{"tool_use_id": "1", "content": "..." }]

    summary, fallback_used = handler._safe_summary(response, tool_calls, tool_results, turn=2)

    assert fallback_used is False
    assert "core/router_rules.py" in summary
