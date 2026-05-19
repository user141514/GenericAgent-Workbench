from __future__ import annotations

from core.tools.schema_registry import (
    align_localized_schema,
    load_runtime_tool_schema,
    resolve_tool_schema_lang,
)


def test_resolve_tool_schema_lang_prefers_env_override(monkeypatch):
    monkeypatch.setenv("GA_LANG", "en")
    monkeypatch.setenv("GA_TOOL_SCHEMA_LANG", "zh")
    assert resolve_tool_schema_lang(llm_name="NativeOAISession/GPT5.5") == "zh"


def test_align_localized_schema_falls_back_to_english_shape():
    base_schema = [
        {
            "type": "function",
            "function": {
                "name": "code_run",
                "description": "Execute code",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "Script"},
                        "timeout": {"type": "integer", "description": "Timeout"},
                    },
                    "required": ["script"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_agent",
                "description": "Run browser workflow",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Task"},
                    },
                    "required": ["task"],
                },
            },
        },
    ]
    localized_schema = [
        {
            "type": "function",
            "function": {
                "name": "code_run",
                "description": "执行代码",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script": {"type": "string", "description": "脚本"},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extra_tool",
                "description": "extra",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    aligned, report = align_localized_schema(base_schema, localized_schema, locale="zh")

    assert [tool["function"]["name"] for tool in aligned] == ["code_run", "browser_agent"]
    assert aligned[0]["function"]["description"] == "执行代码"
    assert aligned[0]["function"]["parameters"]["properties"]["script"]["description"] == "脚本"
    assert aligned[0]["function"]["parameters"]["properties"]["timeout"]["description"] == "Timeout"
    assert aligned[1]["function"]["description"] == "Run browser workflow"
    assert report["missing_tools"] == ["browser_agent"]
    assert report["extra_localized_tools"] == ["extra_tool"]
    assert "code_run.timeout" in report["missing_param_descriptions"]


def test_load_runtime_tool_schema_zh_matches_en_structure():
    en_schema, _ = load_runtime_tool_schema(preferred_lang="en")
    zh_schema, zh_report = load_runtime_tool_schema(preferred_lang="zh")

    assert [tool["function"]["name"] for tool in zh_schema] == [
        tool["function"]["name"] for tool in en_schema
    ]
    assert "browser_agent" in [tool["function"]["name"] for tool in zh_schema]
    assert not zh_report["missing_tools"]
    assert not zh_report["missing_tool_descriptions"]
    assert not zh_report["missing_param_descriptions"]

    for en_tool, zh_tool in zip(en_schema, zh_schema):
        en_props = ((en_tool["function"].get("parameters") or {}).get("properties") or {})
        zh_props = ((zh_tool["function"].get("parameters") or {}).get("properties") or {})
        assert list(zh_props.keys()) == list(en_props.keys())
