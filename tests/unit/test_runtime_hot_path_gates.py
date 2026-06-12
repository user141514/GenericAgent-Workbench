from pathlib import Path


def test_tool_event_ledger_starts_before_tool_dispatch():
    source = Path("core/agent_loop.py").read_text(encoding="utf-8")
    loop_start = source.index("for ii, tc in enumerate(tool_calls):")
    loop_end = source.index("if outcome.should_exit:", loop_start)
    body = source[loop_start:loop_end]

    assert "_ledger.start_call" in body
    assert "handler.dispatch" in body
    assert body.index("_ledger.start_call") < body.index("handler.dispatch")
    assert "_ledger.complete_call" in body


def test_classic_final_response_runs_execution_honesty_gate():
    source = Path("core/ga.py").read_text(encoding="utf-8")
    start = source.index("    def do_no_tool")
    end = source.index("    def do_start_long_term_update", start)
    method = source[start:end]

    assert "evaluate_execution_honesty" in method
    assert method.index("evaluate_execution_honesty") < method.index("Final response to user")
    assert "execution_honesty_repair_enabled" in method
    assert "format_honesty_user_notice" in method
    assert "next_prompt=format_honesty_gate_feedback(honesty)" in method
    assert 'next_prompt=None' in method


def test_openai_final_response_runs_execution_honesty_gate():
    source = Path("core/openai_agentmain.py").read_text(encoding="utf-8")
    assert "def apply_execution_honesty_gate" in source
    assert "build_openai_execution_state" in source
    assert "format_honesty_user_notice" in source
    assert "return format_honesty_user_notice(result), True" in source
    assert "final_text, honesty_blocked = apply_execution_honesty_gate(final_text)" in source
    assert source.count("apply_execution_honesty_gate(final_text)") >= 2


def test_file_tools_use_path_safety_gate_before_filesystem_access():
    source = Path("core/ga.py").read_text(encoding="utf-8")

    for method_name in ("do_file_read", "do_file_write", "do_file_patch"):
        start = source.index(f"    def {method_name}")
        next_def = source.find("\n    def ", start + 1)
        method = source[start: next_def if next_def != -1 else len(source)]
        assert "_resolve_tool_path" in method
        assert method.index("_resolve_tool_path") < method.find("open(") if "open(" in method else True


def test_file_write_has_overwrite_backup_or_hash_preflight():
    source = Path("core/ga.py").read_text(encoding="utf-8")
    start = source.index("    def do_file_write")
    end = source.index("    def do_file_read", start)
    method = source[start:end]

    assert "expected_sha256" in method
    assert "_backup_before_overwrite" in method
    assert "file_backups" in source
    assert method.index("expected_sha256") < method.index("with open(")


def test_file_patch_has_backup_or_hash_preflight():
    source = Path("core/ga.py").read_text(encoding="utf-8")
    start = source.index("    def do_file_patch")
    end = source.index("    def do_file_write", start)
    method = source[start:end]

    assert "expected_sha256" in method
    assert "_backup_before_overwrite" in method
    assert method.index("expected_sha256") < method.index("result = file_patch(")


def test_classic_done_queue_includes_execution_state():
    source = Path("core/agentmain.py").read_text(encoding="utf-8")

    assert "_export_execution_state" in source
    assert "'execution_state': execution_state" in source


def test_openai_final_gate_consumes_executor_execution_state():
    source = Path("core/openai_agentmain.py").read_text(encoding="utf-8")

    assert "_executor_execution_state" in source
    assert "execution_state = item.get(\"execution_state\")" in source
    assert "StateDelta(" in source
    assert "files_changed = tuple(" in source
