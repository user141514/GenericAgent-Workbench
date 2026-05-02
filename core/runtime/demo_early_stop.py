"""Minimal self-check for classic-executor early-stop rules."""

from __future__ import annotations

from .early_stop import should_stop_classic_executor


def main() -> None:
    decision = should_stop_classic_executor(
        user_input="读取 README 第一行标题，然后只用一句话总结项目定位。",
        last_assistant_text=(
            "标题是 `GenericAgent Workbench`。\n"
            "<summary>这是一个构建在 GenericAgent 之上的多智能体工作台。</summary>"
        ),
        tool_results=[{"content": "# GenericAgent Workbench\n\nA multi-agent workbench built on top of GenericAgent."}],
        turn_index=2,
    )
    assert decision.should_stop is True

    decision = should_stop_classic_executor(
        user_input="帮我修改 core/ga.py 并运行测试。",
        last_assistant_text="先检查相关文件并制定修改计划，然后再运行测试。",
        tool_results=[{"content": "No tool output yet."}],
        turn_index=2,
    )
    assert decision.should_stop is False

    decision = should_stop_classic_executor(
        user_input="解释一下 tool call loop。",
        last_assistant_text=(
            "tool call loop 会先让模型生成工具调用，再执行工具，然后把结果拼回下一轮提示，直到模型直接回答。"
        ),
        tool_results=None,
        turn_index=2,
    )
    assert decision.should_stop is True

    decision = should_stop_classic_executor(
        user_input="读取 README 第一行标题，然后只用一句话总结项目定位。",
        last_assistant_text="我需要继续读取文件的剩余部分后再给出最终结论。",
        tool_results=[{"content": "# GenericAgent Workbench"}],
        turn_index=2,
    )
    assert decision.should_stop is False

    decision = should_stop_classic_executor(
        user_input="解释一下 tool call loop。",
        last_assistant_text="这里遇到了工具失败，我需要先恢复后再继续。",
        tool_results=[{"content": 'Error: failed to read file\n{"status": "error"}'}],
        turn_index=2,
    )
    assert decision.should_stop is False

    print("demo_early_stop: OK")


if __name__ == "__main__":
    main()
