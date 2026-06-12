from pathlib import Path

from core.runtime.code_preflight import (
    CODE_PREFLIGHT_ENV_VAR,
    evaluate_code_run_preflight,
)


def test_python_syntax_error_is_blocked(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)

    result = evaluate_code_run_preflight("if True print('x')", "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["python_syntax"]
    assert any("syntax_error" in reason for reason in result.blocked_reasons)
    assert "Code Preflight Blocked" in result.to_tool_message()


def test_valid_python_without_contract_is_allowed(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)

    result = evaluate_code_run_preflight("print('ok')", "python", str(tmp_path))

    assert result.allowed
    assert result.checks["python_syntax"]
    assert result.blocked_reasons == []


def test_missing_required_file_manifest_blocks(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    code = "REQUIRED_FILES = ['e3_inner_cv_tuning.csv']\nprint('run')"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["required_files"]
    assert any("e3_inner_cv_tuning.csv" in reason for reason in result.blocked_reasons)


def test_existing_required_file_manifest_allows(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    (tmp_path / "e3_inner_cv_tuning.csv").write_text("id,value\n1,2\n", encoding="utf-8")
    code = "REQUIRED_FILES = ['e3_inner_cv_tuning.csv']\nprint('run')"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert result.allowed
    assert result.checks["required_files"]


def test_missing_csv_column_manifest_blocks(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    (tmp_path / "features.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    code = "REQUIRED_COLUMNS = {'features.csv': ['a', 'lbc_h10']}\nprint('run')"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["csv_columns"]
    assert any("lbc_h10" in reason for reason in result.blocked_reasons)


def test_pandas_read_csv_missing_file_is_inferred_and_blocked(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    code = "import pandas as pd\ndf = pd.read_csv('e3_inner_cv_tuning.csv')\nprint(df.shape)"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["required_files"]
    assert any("e3_inner_cv_tuning.csv" in reason for reason in result.blocked_reasons)


def test_dataframe_subscript_column_is_inferred_and_blocked(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    (tmp_path / "features.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    code = (
        "import pandas as pd\n"
        "df = pd.read_csv('features.csv')\n"
        "print(df['lbc_h10'].mean())"
    )

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["csv_columns"]
    assert any("features.csv" in reason and "lbc_h10" in reason for reason in result.blocked_reasons)


def test_smoke_required_without_smoke_checked_blocks(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    code = "REQUIRES_SMOKE = True\nprint('full experiment')"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert not result.allowed
    assert not result.checks["smoke_check"]
    assert any("smoke" in reason for reason in result.blocked_reasons)


def test_smoke_required_with_smoke_checked_allows(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    code = "REQUIRES_SMOKE = True\nSMOKE_CHECKED = True\nprint('full experiment')"

    result = evaluate_code_run_preflight(code, "python", str(tmp_path))

    assert result.allowed
    assert result.checks["smoke_check"]


def test_env_flag_can_disable_preflight(monkeypatch, tmp_path):
    monkeypatch.setenv(CODE_PREFLIGHT_ENV_VAR, "0")

    result = evaluate_code_run_preflight("if True print('x')", "python", str(tmp_path))

    assert result.allowed
    assert result.checks == {"enabled": False}


def test_powershell_destructive_command_is_blocked(monkeypatch, tmp_path):
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)

    result = evaluate_code_run_preflight(
        "Remove-Item -Recurse -Force .\\temp",
        "powershell",
        str(tmp_path),
    )

    assert not result.allowed
    assert not result.checks["shell_policy"]
    assert any("destructive_shell_command" in reason for reason in result.blocked_reasons)


def test_ga_code_run_calls_preflight_before_execution():
    source = Path("core/ga.py").read_text(encoding="utf-8")
    start = source.index("    def do_code_run")
    end = source.index("    def do_ask_user", start)
    method = source[start:end]

    assert "evaluate_code_run_preflight" in method
    assert method.index("evaluate_code_run_preflight") < method.index("yield from code_run")
