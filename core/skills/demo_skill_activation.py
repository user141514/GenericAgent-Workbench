from __future__ import annotations

import json
from pathlib import Path

from .skill_activation import build_skill_activation, export_skill_activation
from .skill_prompt_injector import build_optional_sop_context

_MIXED_QUERY = "下一步怎么优化运行速度？"
_HELLO_QUERY = "你好"


def main() -> None:
    context_a = build_optional_sop_context(_MIXED_QUERY, phase="planner")
    assert context_a["selected_skills"] == [
        "performance-optimization",
        "incremental-implementation",
    ], context_a

    activation_a = build_skill_activation(
        user_input=_MIXED_QUERY,
        phase="planner",
        skill_sop_context=context_a,
        run_id="demo-skill-activation",
    )
    assert activation_a.selected_skills == [
        "performance-optimization",
        "incremental-implementation",
    ], activation_a
    assert activation_a.execution_policy["source_skills"] == [
        "performance-optimization",
        "incremental-implementation",
    ], activation_a
    assert activation_a.execution_policy["tool_schema_policy"] == "slim", activation_a
    assert activation_a.execution_policy["max_turns"] == 4, activation_a
    assert activation_a.memory_write_allowed is False, activation_a
    assert "durable memory" in activation_a.memory_write_reason, activation_a

    context_b = build_optional_sop_context(_HELLO_QUERY, phase="planner")
    assert context_b["selected_skills"] == [], context_b

    output_path = export_skill_activation(activation_a)
    assert output_path.exists(), output_path
    last_line = output_path.read_text(encoding="utf-8").strip().splitlines()[-1]
    payload = json.loads(last_line)
    assert payload["activation_id"] == activation_a.activation_id, payload
    assert payload["selected_skills"] == activation_a.selected_skills, payload
    assert payload["execution_policy"]["tool_schema_policy"] == "slim", payload
    assert payload["memory_write_allowed"] is False, payload

    print("demo_skill_activation: OK")


if __name__ == "__main__":
    main()
