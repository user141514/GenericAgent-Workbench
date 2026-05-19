"""Minimal self-check for orchestrator tool-contract filtering."""

from __future__ import annotations

from .tool_contract import (
    build_orchestrator_tool_contract,
    sanitize_runtime_tool_mentions,
    validate_visible_tools,
)


def main() -> None:
    contract = build_orchestrator_tool_contract()

    valid = validate_visible_tools(["run_genericagent_executor"], contract)
    assert "run_genericagent_executor" in valid["valid_tools"]
    assert not valid["unknown_tools"]
    assert not valid["forbidden_tools"]

    forbidden = validate_visible_tools(["transfer_to_code_agent"], contract)
    assert "transfer_to_code_agent" in forbidden["forbidden_tools"]
    assert "transfer_to_code_agent" in forbidden["removed_tools"]

    sanitized = sanitize_runtime_tool_mentions("call transfer_to_code_agent", contract)
    assert "transfer_to_code_agent" not in sanitized
    assert "run_genericagent_executor" in sanitized

    sanitized = sanitize_runtime_tool_mentions("use transfer_to_research_agent", contract)
    assert "transfer_to_research_agent" not in sanitized
    assert "run_genericagent_executor" in sanitized

    print("demo_tool_contract: OK")


if __name__ == "__main__":
    main()
