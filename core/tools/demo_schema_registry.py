"""Self-check for localized tool schema alignment."""

from __future__ import annotations

from .schema_registry import load_runtime_tool_schema


def _tool_names(schema: list[dict]) -> list[str]:
    names: list[str] = []
    for tool in schema:
        fn = tool.get("function") or {}
        names.append(str(fn.get("name") or tool.get("name") or ""))
    return names


def _param_names(tool: dict) -> list[str]:
    fn = tool.get("function") or {}
    params = fn.get("parameters") or {}
    props = params.get("properties") or {}
    return list(props.keys()) if isinstance(props, dict) else []


def main() -> None:
    en_schema, en_report = load_runtime_tool_schema(preferred_lang="en")
    zh_schema, zh_report = load_runtime_tool_schema(preferred_lang="zh")

    assert en_report["locale"] == "en"
    assert zh_report["locale"] == "zh"
    assert _tool_names(en_schema) == _tool_names(zh_schema)
    assert "browser_agent" in _tool_names(zh_schema)
    assert not zh_report["missing_tools"]
    assert not zh_report["missing_tool_descriptions"]
    assert not zh_report["missing_param_descriptions"]

    for en_tool, zh_tool in zip(en_schema, zh_schema):
        assert _param_names(en_tool) == _param_names(zh_tool)
        zh_desc = str((zh_tool.get("function") or {}).get("description") or "").strip()
        assert zh_desc, _tool_names([zh_tool])[0]

    print("demo_schema_registry: OK")


if __name__ == "__main__":
    main()
