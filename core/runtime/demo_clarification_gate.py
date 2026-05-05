"""Demonstration / smoke tests for the Clarification Gate.

Run:
    python -m core.runtime.demo_clarification_gate
"""

from __future__ import annotations

from .clarification_gate import ClarificationDecision, should_allow_clarification


def _assert_decision(
    decision: ClarificationDecision,
    expected_allowed: bool,
    label: str,
) -> None:
    assert decision.allowed == expected_allowed, (
        f"[{label}] expected allowed={expected_allowed}, "
        f"got allowed={decision.allowed}, reason={decision.reason}, "
        f"signals={decision.signals}"
    )
    assert decision.reason, f"[{label}] reason must not be empty"
    print(f"  [{label}] allowed={decision.allowed}, reason={decision.reason[:80]}")


def main() -> None:
    print("demo_clarification_gate:")

    # ── Case A: Vague optimization — should DENY ──────────────────
    print()
    decision_a = should_allow_clarification(
        user_input="帮我优化这个项目",
        question="你想优化哪一部分？",
    )
    _assert_decision(decision_a, False, "A")

    # ── Case B: Dangerous + missing target — should ALLOW ─────────
    print()
    decision_b = should_allow_clarification(
        user_input="删除这个目录",
        question="确认要删除哪个目录吗？",
        context={},  # no target_file / target_object
    )
    _assert_decision(decision_b, True, "B")

    # ── Case C: Vague "fix it" — should ALLOW ────────────────────
    print()
    decision_c = should_allow_clarification(
        user_input="帮我改一下",
        question="请指定要修改什么？",
        context={},  # no target_file
    )
    _assert_decision(decision_c, True, "C")

    # ── Case D: Probing question — should DENY ───────────────────
    print()
    decision_d = should_allow_clarification(
        user_input="下一步怎么优化运行速度？",
        question="你想优化前端还是后端？",
    )
    _assert_decision(decision_d, False, "D")

    # ── Case E: Equiprobable divergent — should ALLOW ────────────
    print()
    decision_e = should_allow_clarification(
        user_input="这里有两个方案，用哪个？",
        question="选 A 还是 B？",
        context={
            "candidates": [
                {"name": "A", "score": 0.51, "action": "rewrite"},
                {"name": "B", "score": 0.49, "action": "small_patch"},
            ],
        },
    )
    _assert_decision(decision_e, True, "E")
    assert decision_e.confidence_gap is not None
    assert decision_e.confidence_gap < 0.15

    # ── Case F: Clear winner — should DENY ──────────────────────
    print()
    decision_f = should_allow_clarification(
        user_input="用哪个方案？",
        question="选 A 还是 B？",
        context={
            "candidates": [
                {"name": "A", "score": 0.8, "action": "small_patch"},
                {"name": "B", "score": 0.2, "action": "rewrite"},
            ],
        },
    )
    _assert_decision(decision_f, False, "F")

    # ── Case G: Extreme cost difference — should ALLOW ───────────
    print()
    decision_g = should_allow_clarification(
        user_input="用哪种方式部署？",
        question="选方案 A 还是 B？",
        context={"cost_ratio": 10.0},
    )
    _assert_decision(decision_g, True, "G")

    # ── Case H: Privacy required — should ALLOW ──────────────────
    print()
    decision_h = should_allow_clarification(
        user_input="访问用户的私人数据",
        question="需要确认是否有权限？",
        context={"requires_privacy_check": True},
    )
    _assert_decision(decision_h, True, "H")

    # ── Case I: Danger keyword but target present — should DENY ──
    print()
    decision_i = should_allow_clarification(
        user_input="删除临时文件",
        question="确认删除吗？",
        context={"target_file": "/tmp/cache"},
    )
    _assert_decision(decision_i, False, "I")

    # ── Case J: Default deny ─────────────────────────────────────
    print()
    decision_j = should_allow_clarification(
        user_input="帮我看看这个项目的结构",
        question="你想看哪个目录？",
    )
    _assert_decision(decision_j, False, "J")

    # ── Verify fallback_instruction on denies ────────────────────
    for decision in [decision_a, decision_d, decision_f, decision_i, decision_j]:
        assert decision.fallback_instruction, (
            f"denied decision missing fallback_instruction: {decision}"
        )

    # ── Verify signals on allows ─────────────────────────────────
    for decision in [decision_b, decision_c, decision_e, decision_g, decision_h]:
        assert decision.signals, (
            f"allowed decision missing signals: {decision}"
        )

    print()
    print("demo_clarification_gate: OK")


if __name__ == "__main__":
    main()
