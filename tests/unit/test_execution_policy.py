"""Unit tests for P2-3 ExecutionPolicy runtime evaluation."""

import pytest

from core.runtime.execution_policy import (
    POLICY_ENV_VAR,
    PolicyDecision,
    evaluate_operation,
    get_policy_mode,
)


# ── Policy mode tests ─────────────────────────────────────────────


def test_default_mode_is_observe(monkeypatch):
    monkeypatch.delenv(POLICY_ENV_VAR, raising=False)
    assert get_policy_mode() == "observe"


def test_explicit_off(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "off")
    assert get_policy_mode() == "off"


def test_explicit_observe(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    assert get_policy_mode() == "observe"


def test_explicit_soft(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "soft")
    assert get_policy_mode() == "soft"


def test_explicit_hard(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "hard")
    assert get_policy_mode() == "hard"


def test_invalid_value_defaults_to_observe(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "invalid")
    assert get_policy_mode() == "observe"


# ── Observe mode: always allow, record only ────────────────────────


def test_observe_normal_request_allowed(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation("帮我写一个 hello world 函数", "")
    assert decision.allowed is True
    assert decision.risk_level == "none"
    assert decision.mode == "observe"


def test_observe_high_risk_recorded_but_allowed(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation("rm -rf /tmp/build 清理构建目录", "")
    assert decision.allowed is True
    assert decision.risk_level == "critical"
    assert len(decision.matched_patterns) > 0


def test_observe_git_reset_recorded_but_allowed(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation("git reset --hard HEAD~3", "")
    assert decision.allowed is True
    assert decision.risk_level == "critical"


def test_observe_pip_install_recorded(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation("pip install requests", "")
    assert decision.allowed is True
    assert decision.risk_level == "medium"


def test_observe_dotenv_access_recorded(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation("读取 .env 文件内容", "")
    assert decision.allowed is True
    assert decision.risk_level == "high"


# ── Off mode ──────────────────────────────────────────────────────


def test_off_mode_no_check(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "off")
    decision = evaluate_operation("rm -rf /", "")
    assert decision.allowed is True
    assert decision.risk_level == "none"


# ── Soft mode: block critical/high ────────────────────────────────


def test_soft_block_critical(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "soft")
    decision = evaluate_operation("git reset --hard HEAD", "")
    assert decision.allowed is False
    assert decision.mode == "soft"


def test_soft_allow_medium(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "soft")
    decision = evaluate_operation("pip install numpy", "")
    assert decision.allowed is True


# ── Hard mode: block any risk ─────────────────────────────────────


def test_hard_block_any_risk(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "hard")
    decision = evaluate_operation("pip install requests", "")
    assert decision.allowed is False


def test_hard_allow_no_risk(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "hard")
    decision = evaluate_operation("读取 README.md", "")
    assert decision.allowed is True


# ── Execution plan scanning ────────────────────────────────────────


def test_risk_in_plan_detected(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation(
        "清理项目",
        "Step 1: rm -rf ./build/\nStep 2: 重新编译",
    )
    assert decision.risk_level == "critical"


def test_mykey_access_in_plan(monkeypatch):
    monkeypatch.setenv(POLICY_ENV_VAR, "observe")
    decision = evaluate_operation(
        "配置 API key",
        "读取 mykey.py 获取当前配置",
    )
    assert decision.risk_level == "high"


# ── PolicyDecision dataclass ──────────────────────────────────────


def test_decision_fields():
    d = PolicyDecision(True, "none", [], "ok", "observe")
    assert d.allowed is True
    assert d.risk_level == "none"
    assert d.matched_patterns == []
