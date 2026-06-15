import time
from pathlib import Path

import pytest

from core.runtime.code_preflight import (
    CODE_PREFLIGHT_ENV_VAR,
    SmokeCache,
    SmokeCacheEntry,
    evaluate_code_run_preflight,
    reset_smoke_cache,
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


# ═══════════════════════════════════════════════════════════════════
# L0: SmokeCache tests
# ═══════════════════════════════════════════════════════════════════


class TestSmokeCache:
    def test_hash_is_stable(self):
        h1 = SmokeCache.hash_code("print(1)")
        h2 = SmokeCache.hash_code("print(1)")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_differs_for_different_code(self):
        h1 = SmokeCache.hash_code("print(1)")
        h2 = SmokeCache.hash_code("print(2)")
        assert h1 != h2

    def test_put_and_get(self):
        c = SmokeCache()
        h = SmokeCache.hash_code("x = 1")
        c.put(h, SmokeCacheEntry(passed=True))
        assert c.get(h) is not None
        assert c.get(h).passed is True

    def test_miss_returns_none(self):
        c = SmokeCache()
        assert c.get("nonexistent") is None

    def test_clear(self):
        c = SmokeCache()
        c.put("abc", SmokeCacheEntry(passed=True))
        c.clear()
        assert len(c) == 0


class TestSmokeCacheIntegration:
    """Tests that the cache actually changes preflight behavior."""

    def test_cache_hit_skips_checks(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()

        smoke_code = "REQUIRES_SMOKE = True\nprint('heavy')\n"
        code_hash = SmokeCache.hash_code(smoke_code)

        # First call: smoke required, not checked → blocked
        result1 = evaluate_code_run_preflight(
            smoke_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert not result1.allowed
        assert not result1.checks["smoke_check"]

        # Cache now has passed=False entry

        # Second call with same code: cache hit → still blocked
        result2 = evaluate_code_run_preflight(
            smoke_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert not result2.allowed
        assert any("cached_smoke_failure" in r for r in result2.blocked_reasons)

    def test_cache_passed_bypasses_checks(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()

        clean_code = "print('hello')\n"
        code_hash = SmokeCache.hash_code(clean_code)

        # First call: no requires_smoke → allowed
        result1 = evaluate_code_run_preflight(
            clean_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert result1.allowed

        # Second call: cache hit with passed=True → skip AST entirely
        result2 = evaluate_code_run_preflight(
            clean_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert result2.allowed
        assert result2.checks.get("cached") is True


# ═══════════════════════════════════════════════════════════════════
# L1: Smoke function detection tests
# ═══════════════════════════════════════════════════════════════════


class TestSmokeFunctionDetection:
    def test_detects_def_smoke(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = (
            "REQUIRES_SMOKE = True\n"
            "def smoke():\n"
            "    print('minimal test')\n"
        )
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        # Should mention the smoke function in blocked reason or suggested_next_step
        assert "smoke()" in result.suggested_next_step

    def test_detects_smoke_test_name(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = (
            "REQUIRES_SMOKE = True\n"
            "def smoke_test():\n"
            "    pass\n"
        )
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        assert "smoke_test()" in result.suggested_next_step

    def test_no_smoke_function_plain_guidance(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = "REQUIRES_SMOKE = True\nprint('heavy')\n"
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        # No specific function name, but still a smoke suggestion
        assert "smoke" in result.suggested_next_step.lower()
        assert "()" not in result.suggested_next_step  # no function name

    def test_smoke_checked_bypasses_detection(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = (
            "REQUIRES_SMOKE = True\n"
            "SMOKE_CHECKED = True\n"
            "def smoke():\n"
            "    pass\n"
        )
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert result.allowed  # SMOKE_CHECKED set, function irrelevant


def test_smoke_cache_does_not_affect_no_cache_path(monkeypatch, tmp_path):
    """Backward compat: passing no cache should work exactly as before."""
    monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
    code = "REQUIRES_SMOKE = True\nprint('x')\n"

    # Without cache — should still block normally
    result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
    assert not result.allowed
    assert "cached" not in result.checks  # no cache metadata leaked
