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

    # ── P1: Semantic hash — smoke markers don't change hash ──

    def test_hash_stable_when_smoke_checked_added(self):
        """Adding SMOKE_CHECKED = True should not change semantic hash."""
        base = "REQUIRES_SMOKE = True\nprint('heavy')\n"
        with_check = "REQUIRES_SMOKE = True\nSMOKE_CHECKED = True\nprint('heavy')\n"
        assert SmokeCache.hash_code(base) == SmokeCache.hash_code(with_check)

    def test_hash_stable_when_smoke_test_passed_added(self):
        base = "REQUIRES_SMOKE = True\nx = 1\n"
        with_check = "REQUIRES_SMOKE = True\nSMOKE_TEST_PASSED = True\nx = 1\n"
        assert SmokeCache.hash_code(base) == SmokeCache.hash_code(with_check)

    def test_hash_stable_when_preflight_smoke_checked_added(self):
        base = "REQUIRES_SMOKE = True\ny = 2\n"
        with_check = "PREFLIGHT_SMOKE_CHECKED = True\nREQUIRES_SMOKE = True\ny = 2\n"
        assert SmokeCache.hash_code(base) == SmokeCache.hash_code(with_check)

    def test_hash_changes_when_logic_changes(self):
        """Changing actual logic (not smoke markers) MUST change hash."""
        h1 = SmokeCache.hash_code("REQUIRES_SMOKE = True\nprint('a')\n")
        h2 = SmokeCache.hash_code("REQUIRES_SMOKE = True\nprint('b')\n")
        assert h1 != h2

    def test_hash_stable_with_different_comments(self):
        """Comments and whitespace don't affect AST, so hash is stable."""
        h1 = SmokeCache.hash_code("print(1)\n")
        h2 = SmokeCache.hash_code("# comment\nprint(1)\n")
        assert h1 == h2

    def test_hash_fallback_on_non_python(self):
        """Shell code falls back to raw text hash."""
        h1 = SmokeCache.hash_code("rm -rf /tmp/*")
        h2 = SmokeCache.hash_code("rm -rf /tmp/*")
        assert h1 == h2
        assert len(h1) == 64

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

    def test_cache_version_default(self):
        """SmokeCacheEntry defaults to current CACHE_VERSION."""
        from core.runtime.code_preflight import CACHE_VERSION
        entry = SmokeCacheEntry(passed=True)
        assert entry.cache_version == CACHE_VERSION

    def test_cache_version_stale_entry_ignored_by_caller(self):
        """Caller should check cache_version before trusting cache."""
        entry = SmokeCacheEntry(passed=True, cache_version=999)
        from core.runtime.code_preflight import CACHE_VERSION
        assert entry.cache_version != CACHE_VERSION
        # The caller (ga.py) is responsible for rejecting stale entries


class TestSmokeCacheIntegration:
    """Cache read/write moved to ga.py — preflight no longer uses cache."""

    def test_preflight_does_not_read_cache(self, monkeypatch, tmp_path):
        """Passing a pre-populated cache to preflight must not change behavior."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()

        smoke_code = "REQUIRES_SMOKE = True\nprint('heavy')\n"
        code_hash = SmokeCache.hash_code(smoke_code)

        # Pre-populate cache with passed=True — preflight must ignore it
        cache.put(code_hash, SmokeCacheEntry(passed=True))

        result = evaluate_code_run_preflight(
            smoke_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        # smoke required, not checked → blocked, regardless of cache
        assert not result.allowed
        assert not result.checks["smoke_check"]
        assert "cached" not in result.checks  # cache metadata must not leak

    def test_preflight_does_not_write_cache(self, monkeypatch, tmp_path):
        """Preflight must not populate the cache — ga.py owns cache writes."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()

        clean_code = "print('hello')\n"
        evaluate_code_run_preflight(
            clean_code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        # Cache must remain empty — preflight no longer writes to it
        assert len(cache) == 0

    def test_preflight_still_works_without_cache(self, monkeypatch, tmp_path):
        """Backward compat: passing no cache must work as before."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = "REQUIRES_SMOKE = True\nprint('x')\n"

        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        assert "cached" not in result.checks  # no cache metadata leaked


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

    def test_action_field_when_smoke_detected(self, monkeypatch, tmp_path):
        """P2: action field must be set when smoke function found + smoke required."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = (
            "REQUIRES_SMOKE = True\n"
            "def smoke():\n"
            "    return True\n"
            "print('main')\n"
        )
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        assert result.action is not None
        assert result.action["type"] == "run_smoke"
        assert result.action["function"] == "smoke"
        assert "smoke()" in result.action["description"]

    def test_no_action_without_smoke_function(self, monkeypatch, tmp_path):
        """P2: no action when no def smoke() exists."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = "REQUIRES_SMOKE = True\nprint('heavy')\n"
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed
        assert result.action is None  # no smoke function → no action

    def test_action_in_to_tool_message(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = (
            "REQUIRES_SMOKE = True\n"
            "def smoke():\n"
            "    pass\n"
        )
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        msg = result.to_tool_message()
        assert "Action:" in msg


# ═══════════════════════════════════════════════════════════════════
# P3: Three-state smoke policy
# ═══════════════════════════════════════════════════════════════════


class TestSmokePolicy:
    def test_policy_off_skips_smoke(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = 'SMOKE_POLICY = "off"\nREQUIRES_SMOKE = True\nprint("risky")\n'
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert result.allowed

    def test_policy_warn_allows_with_warning(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = 'SMOKE_POLICY = "warn"\nREQUIRES_SMOKE = True\nprint("risky")\n'
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert result.allowed
        assert any("smoke_warning" in w for w in result.warnings)

    def test_policy_require_blocks(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = 'SMOKE_POLICY = "require"\nREQUIRES_SMOKE = True\nprint("risky")\n'
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed

    def test_args_override_policy_to_off(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = 'SMOKE_POLICY = "require"\nprint("risky")\n'
        result = evaluate_code_run_preflight(
            code, "python", str(tmp_path), {"smoke_policy": "off"},
        )
        assert result.allowed

    def test_args_override_policy_to_warn(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = 'SMOKE_POLICY = "require"\nREQUIRES_SMOKE = True\nprint("risky")\n'
        result = evaluate_code_run_preflight(
            code, "python", str(tmp_path), {"smoke_policy": "warn"},
        )
        assert result.allowed
        assert any("smoke_warning" in w for w in result.warnings)

    def test_backward_compat_requires_smoke_true(self, monkeypatch, tmp_path):
        """Legacy REQUIRES_SMOKE = True without SMOKE_POLICY → REQUIRE (block)."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = "REQUIRES_SMOKE = True\nprint('risky')\n"
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert not result.allowed

    def test_backward_compat_requires_smoke_false(self, monkeypatch, tmp_path):
        """REQUIRES_SMOKE = False → no smoke needed, allowed."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        code = "REQUIRES_SMOKE = False\nprint('safe')\n"
        result = evaluate_code_run_preflight(code, "python", str(tmp_path), {})
        assert result.allowed

    def test_warn_mode_does_not_populate_cache(self, monkeypatch, tmp_path):
        """WARN mode: preflight must not write to cache (ga.py owns cache)."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()
        code = 'SMOKE_POLICY = "warn"\nREQUIRES_SMOKE = True\nprint("risky")\n'

        r = evaluate_code_run_preflight(
            code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert r.allowed
        assert len(cache) == 0  # preflight must not populate cache

    def test_off_mode_does_not_populate_cache(self, monkeypatch, tmp_path):
        """OFF mode: preflight must not write to cache."""
        monkeypatch.delenv(CODE_PREFLIGHT_ENV_VAR, raising=False)
        cache = SmokeCache()
        code = 'SMOKE_POLICY = "off"\nREQUIRES_SMOKE = True\nprint("risky")\n'

        r = evaluate_code_run_preflight(
            code, "python", str(tmp_path), {}, smoke_cache=cache,
        )
        assert r.allowed
        assert len(cache) == 0  # preflight must not populate cache
