"""Minimal self-check for narrow direct-answer rules."""

from __future__ import annotations

from .direct_answer import try_direct_answer_from_tool_result


def main() -> None:
    decision = try_direct_answer_from_tool_result(
        user_input="读取当前项目 README 的第一行标题，然后只用一句话总结项目定位。",
        tool_results=[
            {
                "content": (
                    "由于设置了show_linenos，以下返回信息为：(行号|)内容 。\n"
                    "[FILE] Total 10 lines\n"
                    "1|# GenericAgent Workbench\n"
                    "2|\n"
                    "3|<p align=\"center\">\n"
                    "4|  <strong>A multi-agent workbench built on top of GenericAgent.</strong><br/>\n"
                )
            }
        ],
        metadata={"tool_names": ["file_read"]},
    )
    assert decision.should_answer is True
    assert "GenericAgent Workbench" in (decision.answer or "")

    decision = try_direct_answer_from_tool_result(
        user_input="读取这个文件第一行。",
        tool_results=[{"content": "[FILE] Total 3 lines\n1|hello world\n2|second line"}],
        metadata={"tool_names": ["file_read"]},
    )
    assert decision.should_answer is True
    assert "hello world" in (decision.answer or "")

    decision = try_direct_answer_from_tool_result(
        user_input="帮我修改 core/ga.py。",
        tool_results=[{"content": "[FILE] Total 3 lines\n1|hello world"}],
        metadata={"tool_names": ["file_read"]},
    )
    assert decision.should_answer is False

    decision = try_direct_answer_from_tool_result(
        user_input="运行测试并告诉我结果。",
        tool_results=[{"content": "tests passed"}],
        metadata={"tool_names": ["code_run"]},
    )
    assert decision.should_answer is False

    decision = try_direct_answer_from_tool_result(
        user_input="读取 README 第一行标题。",
        tool_results=[{"content": 'Error: file not found\n{"status": "error"}'}],
        metadata={"tool_names": ["file_read"]},
    )
    assert decision.should_answer is False

    decision = try_direct_answer_from_tool_result(
        user_input="做一个复杂的架构分析并总结多个文件。",
        tool_results=[{"content": "[FILE] Total 3 lines\n1|# Demo"}],
        metadata={"tool_names": ["file_read"]},
    )
    assert decision.should_answer is False

    print("demo_direct_answer: OK")


if __name__ == "__main__":
    main()
