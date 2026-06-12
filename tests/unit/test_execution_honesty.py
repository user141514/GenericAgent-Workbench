from __future__ import annotations

from core.quality.execution_honesty import (
    ExecutionAction,
    ExecutionState,
    RequestedAction,
    ResponseClaim,
    StateDelta,
    detect_causal_claims,
    detect_state_transition_claims,
    evaluate_execution_honesty,
    format_honesty_gate_feedback,
    format_honesty_user_notice,
)


def test_execution_honesty_exports_from_quality_package():
    from core.quality import ExecutionState as ExportedExecutionState
    from core.quality import evaluate_execution_honesty as exported_gate

    result = exported_gate("No system action claimed.", ExportedExecutionState())

    assert result.allowed is True


def test_detects_chinese_state_and_causal_claims():
    state_claim_text = "\u6211\u8bb0\u4e0b\u4e86\u3002\u5df2\u4fdd\u5b58\u5230 checkpoint\u3002"
    causal_text = "\u8fd9\u8bf4\u660e\u9879\u76ee\u53d1\u751f\u4e86\u53d8\u5316\u3002"

    assert "\u6211\u8bb0\u4e0b\u4e86" in detect_state_transition_claims(state_claim_text)
    assert "\u5df2\u4fdd\u5b58" in detect_state_transition_claims(state_claim_text)
    assert detect_causal_claims(causal_text)


def test_blocks_state_transition_claim_without_trace():
    result = evaluate_execution_honesty(
        "我记下了。已保存到 checkpoint。",
        ExecutionState(
            requested_action=RequestedAction(
                type="memory",
                requires_tool=True,
                required_tool_name="update_working_checkpoint",
                expected_state_delta={"checkpoints_updated": True},
            )
        ),
    )

    assert result.allowed is False
    assert result.action == "block_or_rewrite"
    assert "state_transition_claim_requires_trace" in {f.rule for f in result.findings}
    assert result.unexecuted_commitments[0]["required_next_step"] == "call update_working_checkpoint"


def test_allows_state_transition_claim_with_successful_trace():
    result = evaluate_execution_honesty(
        "已写入 working_checkpoint.txt：用户要求增加 Execution Honesty Gate。",
        ExecutionState(
            actual_actions=[
                ExecutionAction(
                    tool="update_working_checkpoint",
                    input_summary="write checkpoint",
                    output_summary="working_checkpoint.txt updated",
                    status="success",
                    timestamp="2026-06-11T01:00:00",
                )
            ],
            state_delta=StateDelta(checkpoints_updated=True),
        ),
    )

    assert result.allowed is True
    assert result.findings == []


def test_save_claim_requires_material_state_delta_even_with_successful_tool():
    result = evaluate_execution_honesty(
        "\u5df2\u4fdd\u5b58\u5230\u6587\u4ef6\u3002",
        ExecutionState(
            actual_actions=[
                ExecutionAction(
                    tool="file_read",
                    input_summary="read file",
                    output_summary="ok",
                    status="success",
                    timestamp="2026-06-11T01:00:00",
                )
            ]
        ),
    )

    assert result.allowed is False
    assert "state_transition_claim_requires_trace" in {f.rule for f in result.findings}


def test_save_claim_allows_successful_file_delta():
    result = evaluate_execution_honesty(
        "\u5df2\u4fdd\u5b58\u5230\u6587\u4ef6\u3002",
        ExecutionState(
            actual_actions=[
                ExecutionAction(
                    tool="file_write",
                    input_summary="write file",
                    output_summary="ok",
                    status="success",
                    timestamp="2026-06-11T01:00:00",
                )
            ],
            state_delta=StateDelta(files_changed=("notes.md",)),
        ),
    )

    assert result.allowed is True


def test_causal_claim_without_evidence_is_rewrite_required():
    result = evaluate_execution_honesty(
        "这说明项目在报告撰写之后已经有实质性演进。",
        ExecutionState(),
    )

    assert result.allowed is False
    finding = next(f for f in result.findings if f.rule == "causal_claim_requires_evidence_level")
    assert finding.evidence_status == "unsupported"
    assert "当前没有时间线证据" in finding.suggested_rewrite


def test_causal_claim_with_indirect_evidence_is_allowed():
    result = evaluate_execution_honesty(
        "这可能说明项目后来发生了变化，但证据是间接的。",
        ExecutionState(
            response_claims=[
                ResponseClaim(
                    claim="项目后来发生了变化",
                    claim_type="causality",
                    evidence_status="inferred",
                    source="file count mismatch",
                    evidence_type="indirect",
                    confidence=0.45,
                )
            ]
        ),
    )

    assert result.allowed is True


def test_numeric_claim_requires_verification_label():
    result = evaluate_execution_honesty(
        "扫描文件数约 1956 个 Python 文件，所以测试覆盖很充分。",
        ExecutionState(),
    )

    assert result.allowed is False
    assert "quant_claim_requires_verification_status" in {f.rule for f in result.findings}


def test_user_provided_numeric_claim_is_allowed_when_labeled():
    result = evaluate_execution_honesty(
        "基于你提供的数字，暂不独立验证：扫描文件数约 1956 个 Python 文件。",
        ExecutionState(
            response_claims=[
                ResponseClaim(
                    claim="扫描文件数约 1956 个 Python 文件",
                    claim_type="quant",
                    evidence_status="user_provided",
                    source="user audit report",
                    evidence_type="user_provided",
                    confidence=0.5,
                    verified=False,
                )
            ]
        ),
    )

    assert result.allowed is True


def test_honesty_gate_internal_feedback_is_not_user_notice():
    result = evaluate_execution_honesty(
        "已保存。",
        ExecutionState(),
    )

    internal = format_honesty_gate_feedback(result)
    user_notice = format_honesty_user_notice(result)

    assert "[EXECUTION HONESTY GATE]" in internal
    assert "Rewrite the answer" in internal
    assert "[EXECUTION HONESTY GATE]" not in user_notice
    assert "Rewrite the answer" not in user_notice
    assert "suggested_rewrite" not in user_notice
    assert "run the required tool and capture a success trace" not in user_notice
    assert "没有成功的工具证据" in user_notice
