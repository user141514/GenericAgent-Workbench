from __future__ import annotations

from .problem_framing import build_problem_framing_context, should_inject_problem_framing


def main() -> None:
    # ── Case A: AI capability question ──────────────────────────
    case_a = build_problem_framing_context(
        "我想人为去逼迫人工智能提升对问题的理解能力，怎么做？"
    )
    assert case_a["matched"] is True, f"case_a should match: {case_a}"
    assert case_a["block"], f"case_a should have block: {case_a}"
    assert case_a["frame"] in ("ai_capability", "improvement"), (
        f"case_a frame expected ai_capability/improvement, got {case_a['frame']}"
    )

    # ── Case B: Next-step optimization ──────────────────────────
    case_b = build_problem_framing_context("下一步怎么优化这个项目？")
    assert case_b["matched"] is True, f"case_b should match: {case_b}"
    assert case_b["block"], f"case_b should have block: {case_b}"

    # ── Case C: Read shortcut — should NOT match ────────────────
    case_c = should_inject_problem_framing("读取 README 第一行")
    assert case_c is False, f"case_c should NOT match: {case_c}"

    # ── Case D: Greeting — should NOT match ─────────────────────
    case_d = should_inject_problem_framing("你好")
    assert case_d is False, f"case_d should NOT match: {case_d}"

    # ── Case E: Implementation — plausible match via _UNDERSTANDING_TRIGGERS ──
    # "修复" is in IMPLEMENTATION triggers, not primary framing triggers
    case_e = should_inject_problem_framing("帮我修复 core/ga.py 的 bug")
    # "修复" / "检查" do not match top-level triggers — this should be False
    assert case_e is False, f"case_e should NOT match (implementation only): {case_e}"

    # ── Case F: Architecture discussion ─────────────────────────
    case_f = build_problem_framing_context("这个项目的架构有什么问题？")
    assert case_f["matched"] is True, f"case_f should match: {case_f}"
    assert case_f["frame"] == "architecture", (
        f"case_f frame expected architecture, got {case_f['frame']}"
    )

    # ── Case G: Understanding / debug ───────────────────────────
    case_g = should_inject_problem_framing("为什么这个模块运行这么慢？")
    assert case_g is True, f"case_g should match: {case_g}"

    # ── Boundary: max_chars respected ───────────────────────────
    for case in [case_a, case_b, case_f]:
        assert case["chars"] <= 1800, f"chars exceeded: {case}"

    print("demo_problem_framing: OK")


if __name__ == "__main__":
    main()
