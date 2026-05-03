from __future__ import annotations

from .answer_quality_context import build_answer_quality_context


def main() -> None:
    case_a = build_answer_quality_context("这样看它的输出质量和你也有差距，怎么去改进呢？")
    assert case_a["matched"] is True, case_a
    assert case_a["block"], case_a

    case_b = build_answer_quality_context("下一步怎么优化这个项目？")
    assert case_b["matched"] is True, case_b
    assert case_b["block"], case_b

    case_c = build_answer_quality_context("读取 README 第一行")
    assert case_c["matched"] is False, case_c
    assert case_c["block"] == "", case_c

    case_d = build_answer_quality_context("你好")
    assert case_d["matched"] is False, case_d
    assert case_d["block"] == "", case_d

    case_e = build_answer_quality_context("帮我修改 core/ga.py 并运行测试")
    assert case_e["matched"] is False, case_e
    assert case_e["block"] == "", case_e

    assert case_a["chars"] <= 1800, case_a

    print("demo_answer_quality_context: OK")


if __name__ == "__main__":
    main()
