import json

from core.llmcore import ToolClient


class _DummyBackend:
    name = "dummy"
    model = "dummy"

    def ask(self, *_args, **_kwargs):
        raise AssertionError("This test only builds prompts; it must not call the backend.")


def _tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "file_read",
                "description": "Read a file.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


def _tools_json(tools):
    return json.dumps(tools, ensure_ascii=False, separators=(",", ":"))


def test_tool_cache_budget_resets_when_refresh_is_required():
    tools = _tools()
    client = ToolClient(_DummyBackend(), auto_save_tokens=True)
    client.last_tools = _tools_json(tools)
    client.total_cd_tokens = 8999

    client._build_protocol_prompt(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "x" * 200},
        ],
        tools,
    )

    assert client.last_tools == ""
    assert client.total_cd_tokens == 0


def test_tool_cache_budget_counts_built_prompt_once():
    tools = _tools()
    client = ToolClient(_DummyBackend(), auto_save_tokens=True)
    client.last_tools = _tools_json(tools)

    client._build_protocol_prompt(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ],
        tools,
    )

    first_total = client.total_cd_tokens
    client._build_protocol_prompt(
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ],
        tools,
    )

    assert client.total_cd_tokens == first_total * 2
