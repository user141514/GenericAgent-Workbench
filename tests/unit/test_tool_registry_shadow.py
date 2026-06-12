from __future__ import annotations

from core.ga import GenericAgentHandler
from core.tools.handler_registry import (
    discover_handler_tool_names,
    extract_schema_tool_names,
    validate_tool_registry_shadow,
)
from core.tools.schema_registry import load_runtime_tool_schema


class FakeHandler:
    def do_code_run(self, args, response):
        return None

    def do_no_tool(self, args, response):
        return None

    def do_orphan_handler(self, args, response):
        return None

    def helper(self):
        return None


def test_extract_schema_tool_names_handles_function_and_legacy_shapes():
    schema = [
        {"type": "function", "function": {"name": "code_run"}},
        {"name": "file_read"},
        {"type": "function", "function": {"name": ""}},
        {"type": "function", "function": {}},
    ]

    assert extract_schema_tool_names(schema) == ("code_run", "file_read")


def test_validate_tool_registry_shadow_reports_mismatches_without_dispatching():
    schema = [
        {"type": "function", "function": {"name": "code_run"}},
        {"type": "function", "function": {"name": "file_read"}},
    ]

    report = validate_tool_registry_shadow(FakeHandler, schema)

    assert report.ok is False
    assert report.schema_without_handler == ("file_read",)
    assert report.handler_without_schema == ("orphan_handler",)
    assert report.internal_handlers == ("no_tool",)
    assert report.to_dict()["schema_tool_count"] == 2


def test_current_generic_handler_matches_runtime_tool_schema():
    schema, _ = load_runtime_tool_schema(preferred_lang="en")

    report = validate_tool_registry_shadow(GenericAgentHandler, schema)

    assert report.ok is True
    assert report.schema_without_handler == ()
    assert report.handler_without_schema == ()
    assert report.internal_handlers == ("no_tool",)
    assert "code_run" in discover_handler_tool_names(GenericAgentHandler)
