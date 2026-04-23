from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import locale
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, cast

from .router_rules import RouterRules, RouteResult

os.environ.setdefault(
    "GA_LANG",
    "zh"
    if any(k in (locale.getlocale()[0] or "").lower() for k in ("zh", "chinese"))
    else "en",
)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
elif hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
elif hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = PROJECT_ROOT
sys.path.append(SCRIPT_DIR)
CLAUDE_SETTINGS_PATH = os.path.expanduser(r"~/.claude/settings.json")
CAPABILITY_BRIEF = (
    "This application is not a plain text-only chatbot. "
    "It has a multi-agent workflow and an executor delegated to the classic GenericAgent runtime. "
    "Available execution capabilities include reading files, patching files, running code, "
    "using browser/web tools, and other GenericAgent-mounted tools when the executor is invoked. "
    "If the user asks what tools, skills, or operational abilities are available, describe these "
    "integrated capabilities accurately instead of claiming you have no tools."
)
SUMMARY_PROTOCOL_ZH = (
    "### 行动规范（持续有效）\n"
    "1. 在每次交接、调用工具或最终回答前，先输出一行 <summary>...</summary>。\n"
    "2. <summary> 必须极简且事实化，概括上次结果新信息 + 本次意图。\n"
    "3. 再输出正文；不要省略 summary。"
)
SUMMARY_PROTOCOL_EN = (
    "### Action Protocol (always in effect)\n"
    "1. Before every handoff, tool call, or final answer, emit one line of <summary>...</summary>.\n"
    "2. The <summary> must be minimal and factual: new information from the last result + current intent.\n"
    "3. Then write the body; do not omit the summary."
)

_ensure_path_ready = False
if not _ensure_path_ready:
    repo_src = os.path.join(os.path.dirname(SCRIPT_DIR), "openai-agents-python", "src")
    if os.path.isdir(repo_src) and repo_src not in sys.path:
        sys.path.insert(0, repo_src)
    _ensure_path_ready = True

try:
    from agents import Model
except Exception:  # pragma: no cover - runtime fallback until startup validation runs.
    class Model:  # type: ignore[no-redef]
        pass


class _CompatBackend:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []


class _CompatLLMClient:
    def __init__(self) -> None:
        self.last_tools = ""
        self.backend = _CompatBackend()


def smart_format(data: Any, max_str_len: int = 100, omit_str: str = " ... ") -> str:
    text = data if isinstance(data, str) else str(data)
    if len(text) < max_str_len + len(omit_str) * 2:
        return text
    return f"{text[: max_str_len // 2]}{omit_str}{text[-max_str_len // 2 :]}"


def _summary_protocol() -> str:
    return SUMMARY_PROTOCOL_EN if os.environ.get("GA_LANG") == "en" else SUMMARY_PROTOCOL_ZH


def _extract_summary_line(text: str) -> str:
    match = re.search(r"<summary>\s*(.*?)\s*</summary>", text or "", re.DOTALL | re.IGNORECASE)
    if match:
        summary = " ".join(match.group(1).split()).strip()
        if summary:
            return smart_format(summary, max_str_len=100)
    stripped = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text or "", flags=re.IGNORECASE)
    stripped = re.sub(r"</?summary>", "", stripped, flags=re.IGNORECASE)
    stripped = re.sub(r"\*\*LLM Running \(Turn \d+\) \.\.\.\*\*", "", stripped)
    for line in stripped.splitlines():
        line = line.strip()
        if line:
            return smart_format(line, max_str_len=100)
    return ""


def _working_memory_message(history: list[str]) -> str:
    if not history:
        return ""
    h_str = "\n".join(history[-20:])
    return (
        "### [WORKING MEMORY]\n"
        f"<history>\n{h_str}\n</history>\n"
        "Use this as compressed recent context. Keep the next <summary> consistent with it."
    )


def _classic_executor_plan(reason: str = "") -> str:
    plan = (
        "Complete the user's request directly with the classic GenericAgent runtime. "
        "Ignore orchestration-only artifacts and produce the final user-facing answer."
    )
    reason = " ".join((reason or "").split()).strip()
    if reason:
        plan += f"\nPrevious orchestration issue: {smart_format(reason, max_str_len=400)}"
    return plan


def _should_fallback_to_classic(route_target: str, final_text: str = "", exc: BaseException | None = None) -> bool:
    if exc is not None:
        msg = f"{type(exc).__name__}: {exc}".lower()
        if "run_genericagent_executor" in msg or "not found in agent chat_specialist" in msg:
            return True
        if route_target != "executor":
            return False
        return any(
            token in msg
            for token in (
                "tool",
                "handoff",
                "modelbehaviorerror",
                "not found in agent",
                "run_loop",
            )
        )
    if route_target != "executor":
        return False
    normalized = " ".join((final_text or "").split()).strip().lower()
    if not normalized:
        return True
    internal_markers = (
        "transfer_to_",
        "ask_planner",
        "ask_executor",
        "run_genericagent_executor",
        "workflow_coordinator",
    )
    return len(normalized) < 400 and any(marker in normalized for marker in internal_markers)


def consume_file(dr: str | None, file: str) -> str | None:
    if dr:
        path = os.path.join(dr, file)
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            os.remove(path)
            return content
    return None


def format_error(exc: BaseException) -> str:
    exc_type, _, exc_tb = sys.exc_info()
    if exc_tb is not None:
        tb = traceback.extract_tb(exc_tb)
        if tb:
            frame = tb[-1]
            return (
                f"{exc_type.__name__}: {exc} @ "
                f"{os.path.basename(frame.filename)}:{frame.lineno}, {frame.name}"
            )
    return f"{type(exc).__name__}: {exc}"


def _ensure_openai_agents_on_path() -> None:
    repo_src = os.path.join(os.path.dirname(SCRIPT_DIR), "openai-agents-python", "src")
    if os.path.isdir(repo_src) and repo_src not in sys.path:
        sys.path.insert(0, repo_src)


def _load_json_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _load_mykeys() -> dict[str, Any]:
    py_path = os.path.join(SCRIPT_DIR, "mykey.py")
    if os.path.exists(py_path):
        spec = importlib.util.spec_from_file_location("ga_mykey", py_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Unable to load mykey.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {k: v for k, v in vars(module).items() if not k.startswith("_")}

    json_path = os.path.join(SCRIPT_DIR, "mykey.json")
    if os.path.exists(json_path):
        return _load_json_file(json_path)

    return {}


def _load_claude_settings() -> dict[str, Any]:
    return _load_json_file(CLAUDE_SETTINGS_PATH)


def _strip_url(url: str | None) -> str | None:
    if not url:
        return None
    return str(url).rstrip("/")


def _normalize_openai_base_url(base_url: str | None) -> str | None:
    stripped = _strip_url(base_url)
    if not stripped:
        return None
    if "/v1" not in stripped:
        return f"{stripped}/v1"
    return stripped


def _infer_backend_kind(name: str, base_url: str | None, model: str | None) -> str | None:
    lname = name.lower()
    lbase = (base_url or "").lower()
    lmodel = (model or "").lower()
    if any(token in lname for token in ("claude", "anthropic")):
        return "native_claude"
    if any(token in lbase for token in ("anthropic", "/messages")):
        return "native_claude"
    if any(token in lmodel for token in ("claude", "anthropic")):
        return "native_claude"
    if any(token in lname for token in ("oai", "openai", "gpt")):
        return "native_oai"
    if any(token in lbase for token in ("openai", "/v1", "chat/completions", "responses")):
        return "native_oai"
    return None


def _candidate_priority(variant: dict[str, Any]) -> tuple[int, int, int, str]:
    label = str(variant.get("label", "")).lower()
    backend_kind = variant.get("backend_kind")
    source = variant.get("source")
    return (
        0 if backend_kind == "native_claude" else 1,
        0 if source == "mykey.py" else 1,
        0 if "native" in label else 1,
        label,
    )


def _make_variant(
    *,
    label: str,
    backend_kind: str,
    api_key: str,
    base_url: str | None,
    model: str | None,
    source: str,
    stream: bool | None = None,
    connect_timeout: int | None = None,
    read_timeout: int | None = None,
) -> dict[str, Any] | None:
    if not api_key or not base_url or not model:
        return None
    normalized_base_url = (
        _strip_url(base_url)
        if backend_kind == "native_claude"
        else _normalize_openai_base_url(base_url)
    )
    if not normalized_base_url:
        return None
    variant = {
        "label": label,
        "backend_kind": backend_kind,
        "api_key": api_key,
        "base_url": normalized_base_url,
        "model": model,
        "source": source,
    }
    if stream is not None:
        variant["stream"] = stream
    if connect_timeout is not None:
        variant["connect_timeout"] = connect_timeout
    if read_timeout is not None:
        variant["read_timeout"] = read_timeout
    return variant


def _resolve_model_variants() -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    for name, cfg in _load_mykeys().items():
        if not isinstance(cfg, dict):
            continue
        api_key = str(cfg.get("apikey") or "").strip()
        base_url = str(cfg.get("apibase") or "").strip()
        model = str(cfg.get("model") or cfg.get("name") or "").strip()
        backend_kind = _infer_backend_kind(name, base_url, model)
        if not backend_kind:
            continue
        variant = _make_variant(
            label=name,
            backend_kind=backend_kind,
            api_key=api_key,
            base_url=base_url,
            model=model,
            source="mykey.py",
            stream=cfg.get("stream"),
            connect_timeout=cfg.get("connect_timeout"),
            read_timeout=cfg.get("read_timeout"),
        )
        if variant:
            variants.append(variant)

    settings_env = _load_claude_settings().get("env", {})
    if isinstance(settings_env, dict):
        anthropic_variant = _make_variant(
            label="claude-settings/anthropic",
            backend_kind="native_claude",
            api_key=str(settings_env.get("ANTHROPIC_AUTH_TOKEN") or "").strip(),
            base_url=str(settings_env.get("ANTHROPIC_BASE_URL") or "").strip(),
            model=str(settings_env.get("ANTHROPIC_MODEL") or "").strip(),
            source="~/.claude/settings.json",
        )
        if anthropic_variant:
            variants.append(anthropic_variant)

        openai_variant = _make_variant(
            label="claude-settings/openai",
            backend_kind="native_oai",
            api_key=str(settings_env.get("OPENAI_API_KEY") or "").strip(),
            base_url=str(settings_env.get("OPENAI_BASE_URL") or "").strip(),
            model=str(settings_env.get("OPENAI_MODEL") or "").strip(),
            source="~/.claude/settings.json",
        )
        if openai_variant:
            variants.append(openai_variant)

    env_anthropic_variant = _make_variant(
        label="env/anthropic",
        backend_kind="native_claude",
        api_key=str(os.environ.get("ANTHROPIC_AUTH_TOKEN") or "").strip(),
        base_url=str(os.environ.get("ANTHROPIC_BASE_URL") or "").strip(),
        model=str(os.environ.get("ANTHROPIC_MODEL") or "").strip(),
        source="env",
    )
    if env_anthropic_variant:
        variants.append(env_anthropic_variant)

    env_openai_variant = _make_variant(
        label="env/openai",
        backend_kind="native_oai",
        api_key=str(os.environ.get("OPENAI_API_KEY") or "").strip(),
        base_url=str(os.environ.get("OPENAI_BASE_URL") or "").strip(),
        model=str(os.environ.get("OPENAI_MODEL") or "").strip(),
        source="env",
    )
    if env_openai_variant:
        variants.append(env_openai_variant)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for variant in sorted(variants, key=_candidate_priority):
        key = (
            str(variant["backend_kind"]),
            str(variant["api_key"]),
            str(variant["base_url"]),
            str(variant["model"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(variant)
    return deduped


def _log_exchange(prompt: str, response: str, input_items: list | None = None) -> None:
    log_dir = os.path.join(SCRIPT_DIR, "temp", "model_responses_openai")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"model_responses_{os.getpid()}.txt")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"=== USER ===\n{prompt}\n")
        f.write(f"=== Response === {ts}\n{response}\n")
        if input_items:
            try:
                import json
                f.write(f"=== INPUT_ITEMS ===\n{json.dumps(input_items, ensure_ascii=False, indent=2)}\n")
            except Exception:
                pass
        f.write("\n")


def _restored_lines_to_inputs(restored: list[str]) -> list[dict[str, str]]:
    inputs: list[dict[str, str]] = []
    for line in restored:
        if line.startswith("[USER]: "):
            inputs.append({"role": "user", "content": line[8:]})
        elif line.startswith("[Agent] "):
            inputs.append({"role": "assistant", "content": line[8:]})
    return inputs


def _input_items_to_history_lines(input_items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in input_items or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _tool_message_content_to_text(item.get("content"))
        if not text and "output" in item:
            text = _tool_message_content_to_text(item.get("output"))
        text = (text or "").strip()
        if not text:
            continue
        prefix = "[USER]: " if role == "user" else "[Agent] "
        line = prefix + text
        if lines:
            same_role = (role == "user" and lines[-1].startswith("[USER]: ")) or (
                role == "assistant" and lines[-1].startswith("[Agent] ")
            )
            if same_role:
                lines[-1] += "\n\n" + text
                continue
        lines.append(line)
    return lines


def _message_content_to_claude_blocks(content: Any) -> list[dict[str, Any]]:
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return [{"type": "text", "text": str(content)}]

    blocks: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            blocks.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            blocks.append({"type": "text", "text": str(part)})
            continue
        part_type = part.get("type")
        if part_type in {"text", "input_text", "output_text"}:
            blocks.append({"type": "text", "text": str(part.get("text") or "")})
        elif part_type == "refusal":
            blocks.append({"type": "text", "text": str(part.get("refusal") or "")})
        elif part_type == "image_url":
            image_url = (part.get("image_url") or {}).get("url", "")
            if image_url:
                blocks.append({"type": "text", "text": f"[image] {image_url}"})
        else:
            text_value = part.get("text")
            if isinstance(text_value, str) and text_value:
                blocks.append({"type": "text", "text": text_value})
    return blocks


def _tool_message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict):
            if part.get("type") in {"text", "input_text", "output_text"}:
                parts.append(str(part.get("text") or ""))
            elif part.get("type") == "refusal":
                parts.append(str(part.get("refusal") or ""))
    return "\n".join(p for p in parts if p)


def _chat_messages_to_claude_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    claude_messages: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            claude_messages.append({"role": "user", "content": list(pending_tool_results)})
            pending_tool_results = []

    for message in messages:
        role = str(message.get("role") or "")
        if role == "system":
            continue
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(message.get("tool_call_id") or ""),
                    "content": _tool_message_content_to_text(message.get("content")),
                }
            )
            continue
        if role == "assistant":
            flush_tool_results()
            content_blocks = _message_content_to_claude_blocks(message.get("content"))
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function", {})
                arguments = function.get("arguments") or "{}"
                try:
                    parsed_arguments = (
                        json.loads(arguments) if isinstance(arguments, str) else arguments
                    )
                except Exception:
                    parsed_arguments = {"_raw": arguments}
                if not isinstance(parsed_arguments, dict):
                    parsed_arguments = {"_raw": str(parsed_arguments)}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(tool_call.get("id") or ""),
                        "name": str(function.get("name") or ""),
                        "input": parsed_arguments,
                    }
                )
            if not content_blocks:
                content_blocks = [{"type": "text", "text": ""}]
            claude_messages.append({"role": "assistant", "content": content_blocks})
            continue
        if role == "user":
            content_blocks = list(pending_tool_results)
            pending_tool_results = []
            content_blocks.extend(_message_content_to_claude_blocks(message.get("content")))
            if not content_blocks:
                content_blocks = [{"type": "text", "text": ""}]
            claude_messages.append({"role": "user", "content": content_blocks})

    flush_tool_results()
    if not claude_messages:
        claude_messages.append({"role": "user", "content": [{"type": "text", "text": ""}]})
    return claude_messages


def _inject_turn_markers(text: str, start_turn: int = 1) -> str:
    if not text.strip():
        return text
    if "LLM Running (Turn" in text:
        return text

    section_patterns = [
        ("Plan", r"(?mi)^(?:#+\s*)?Plan\s*:?\s*$"),
        ("Execution", r"(?mi)^(?:#+\s*)?Execution\s*:?\s*$"),
        ("Verification", r"(?mi)^(?:#+\s*)?Verification\s*:?\s*$"),
        ("Final Answer", r"(?mi)^(?:#+\s*)?Final Answer\s*:?\s*$"),
    ]
    matches: list[tuple[int, str, int]] = []
    for label, pattern in section_patterns:
        match = re.search(pattern, text)
        if match:
            matches.append((match.start(), label, match.end()))

    if not matches:
        return f"**LLM Running (Turn {start_turn}) ...**\n\n{text}"

    matches.sort(key=lambda item: item[0])
    rebuilt: list[str] = []
    for idx, (start, _label, _end) in enumerate(matches):
        next_start = matches[idx + 1][0] if idx + 1 < len(matches) else len(text)
        chunk = text[start:next_start].strip()
        if not chunk:
            continue
        rebuilt.append(f"**LLM Running (Turn {start_turn + len(rebuilt)}) ...**\n\n{chunk}")

    if rebuilt:
        prefix = text[: matches[0][0]].strip()
        if prefix:
            rebuilt.insert(0, f"**LLM Running (Turn {start_turn}) ...**\n\n{prefix}")
        return "\n\n".join(rebuilt)

    return f"**LLM Running (Turn {start_turn}) ...**\n\n{text}"


def _extract_classic_executor_report(text: str) -> str:
    if not text:
        return ""
    if "</summary>" in text:
        tail = text.rsplit("</summary>", 1)[-1].strip()
        if tail:
            return tail
    sections = [
        part.strip()
        for part in re.split(r"\*\*LLM Running \(Turn \d+\) \.\.\.\*\*\s*", text)
        if part.strip()
    ]
    if sections:
        return sections[-1]
    return text.strip()


class GenericAgentSDKModel(Model):
    def __init__(self, variant: dict[str, Any]) -> None:
        self.variant = dict(variant)

    def _build_session(
        self,
        *,
        system_instructions: str | None,
        model_settings: Any,
        tools: list[Any],
        handoffs: list[Any],
        force_stream: bool | None = None,
    ) -> tuple[Any, list[dict[str, Any]]]:
        from agents.models.chatcmpl_converter import Converter
        from .llmcore import ClaudeSession, LLMSession, NativeClaudeSession, NativeOAISession

        cfg = {
            "name": self.variant["label"],
            "apikey": self.variant["api_key"],
            "apibase": self.variant["base_url"],
            "model": self.variant["model"],
            "stream": False if force_stream is None else bool(force_stream),
            "temperature": model_settings.temperature
            if model_settings.temperature is not None
            else 1,
            "max_tokens": model_settings.max_tokens or 8192,
            "max_retries": 3,
            "connect_timeout": self.variant.get("connect_timeout", 30),
            "read_timeout": self.variant.get("read_timeout", 300),
        }
        converted_tools = [Converter.tool_to_openai(tool) for tool in tools] if tools else []
        for handoff in handoffs:
            converted_tools.append(Converter.convert_handoff_tool(handoff))

        if self.variant["backend_kind"] == "native_claude":
            session_cls = NativeClaudeSession
        else:
            session_cls = NativeOAISession if converted_tools else LLMSession

        session = session_cls(cfg)
        session.system = system_instructions or ""
        session.tools = converted_tools
        return session, converted_tools

    def _prepare_request(
        self,
        *,
        system_instructions: str | None,
        input_items: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        handoffs: list[Any],
        force_stream: bool | None = None,
    ) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
        from agents.models.chatcmpl_converter import Converter

        session, converted_tools = self._build_session(
            system_instructions=system_instructions,
            model_settings=model_settings,
            tools=tools,
            handoffs=handoffs,
            force_stream=force_stream,
        )
        chat_messages = Converter.items_to_messages(
            input_items,
            model=self.variant["model"],
            preserve_thinking_blocks=True,
            preserve_tool_output_all_content=True,
        )
        claude_messages = _chat_messages_to_claude_messages(chat_messages)
        return session, converted_tools, claude_messages

    @staticmethod
    def _zero_response_usage() -> Any:
        from openai.types.responses import ResponseUsage
        from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

        return ResponseUsage(
            input_tokens=0,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens=0,
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            total_tokens=0,
        )

    @staticmethod
    def _content_blocks_to_output_items(content_blocks: list[dict[str, Any]]) -> list[Any]:
        from agents.models.fake_id import FAKE_RESPONSES_ID
        from openai.types.responses import (
            ResponseFunctionToolCall,
            ResponseOutputMessage,
            ResponseOutputText,
        )

        message_parts: list[Any] = []
        for block in content_blocks:
            if block.get("type") != "text":
                continue
            text = str(block.get("text") or "")
            if not text:
                continue
            message_parts.append(
                ResponseOutputText(
                    text=text,
                    type="output_text",
                    annotations=[],
                    logprobs=[],
                )
            )

        output_items: list[Any] = []
        if message_parts:
            output_items.append(
                ResponseOutputMessage(
                    id=FAKE_RESPONSES_ID,
                    content=message_parts,
                    role="assistant",
                    type="message",
                    status="completed",
                )
            )

        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            arguments = block.get("input", {})
            if isinstance(arguments, str):
                arguments_json = arguments
            else:
                arguments_json = json.dumps(arguments, ensure_ascii=False)
            output_items.append(
                ResponseFunctionToolCall(
                    id=FAKE_RESPONSES_ID,
                    call_id=str(block.get("id") or ""),
                    arguments=arguments_json or "{}",
                    name=str(block.get("name") or ""),
                    type="function_call",
                    status="completed",
                )
            )

        if output_items:
            return output_items

        return [
            ResponseOutputMessage(
                id=FAKE_RESPONSES_ID,
                content=[],
                role="assistant",
                type="message",
                status="completed",
            )
        ]

    @staticmethod
    def _retryable_error_text(content_blocks: list[dict[str, Any]]) -> str | None:
        if len(content_blocks) != 1:
            return None
        block = content_blocks[0]
        if block.get("type") != "text":
            return None
        text = str(block.get("text") or "")
        if not text.startswith("Error:"):
            return None
        lowered = text.lower()
        retry_markers = (
            "ssl",
            "eof",
            "timeout",
            "connectionerror",
            "httpsconnectionpool",
            "max retries exceeded",
            "remote end closed",
            "connection aborted",
            "read timed out",
            "connecttimeout",
            "temporarily unavailable",
        )
        return text if any(marker in lowered for marker in retry_markers) else None

    def _collect_content_blocks(
        self,
        session: Any,
        claude_messages: list[dict[str, Any]],
        *,
        on_chunk: Any | None = None,
    ) -> list[dict[str, Any]]:
        max_retries = max(0, int(getattr(session, "max_retries", 0)))
        for attempt in range(max_retries + 1):
            buffered_first_chunk: str | None = None
            streamed_non_error_chunk = False
            generator = session.raw_ask(claude_messages)
            try:
                while True:
                    chunk = str(next(generator) or "")
                    if not chunk:
                        continue
                    if (
                        on_chunk is not None
                        and buffered_first_chunk is None
                        and not streamed_non_error_chunk
                        and chunk.startswith("Error:")
                    ):
                        buffered_first_chunk = chunk
                        continue
                    if buffered_first_chunk is not None and on_chunk is not None:
                        on_chunk(buffered_first_chunk)
                        streamed_non_error_chunk = True
                        buffered_first_chunk = None
                    if on_chunk is not None:
                        on_chunk(chunk)
                        streamed_non_error_chunk = True
            except StopIteration as stop:
                raw_value = stop.value or []
                content_blocks = cast(
                    list[dict[str, Any]],
                    raw_value if isinstance(raw_value, list) else [],
                )
                retryable_error = self._retryable_error_text(content_blocks)
                if retryable_error and not streamed_non_error_chunk and attempt < max_retries:
                    time.sleep(min(5.0, 1.5 * (attempt + 1)))
                    continue
                if buffered_first_chunk is not None and on_chunk is not None:
                    on_chunk(buffered_first_chunk)
                return content_blocks
        return [{"type": "text", "text": "Error: unexpected retry state"}]

    def _run_sync(
        self,
        *,
        system_instructions: str | None,
        input_items: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        handoffs: list[Any],
    ) -> Any:
        from agents.usage import Usage
        session, _, claude_messages = self._prepare_request(
            system_instructions=system_instructions,
            model_settings=model_settings,
            input_items=input_items,
            tools=tools,
            handoffs=handoffs,
            force_stream=False,
        )

        return {
            "output": self._content_blocks_to_output_items(
                self._collect_content_blocks(session, claude_messages)
            ),
            "usage": Usage(requests=1),
        }

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> Any:
        from agents.items import ModelResponse

        response = await asyncio.to_thread(
            self._run_sync,
            system_instructions=system_instructions,
            input_items=input,
            model_settings=model_settings,
            tools=tools,
            handoffs=handoffs,
        )
        return ModelResponse(
            output=response["output"],
            usage=response["usage"],
            response_id=None,
        )

    async def close(self) -> None:
        return None

    async def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ):
        from agents.models.fake_id import FAKE_RESPONSES_ID
        from openai.types.responses import (
            Response,
            ResponseCompletedEvent,
            ResponseContentPartAddedEvent,
            ResponseContentPartDoneEvent,
            ResponseCreatedEvent,
            ResponseOutputItemAddedEvent,
            ResponseOutputItemDoneEvent,
            ResponseOutputMessage,
            ResponseOutputText,
            ResponseTextDeltaEvent,
            ResponseTextDoneEvent,
        )

        session, converted_tools, claude_messages = self._prepare_request(
            system_instructions=system_instructions,
            input_items=input,
            model_settings=model_settings,
            tools=tools,
            handoffs=handoffs,
            force_stream=True,
        )

        loop = asyncio.get_running_loop()
        stream_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        stream_closed = threading.Event()

        def put_from_worker(kind: str, payload: Any) -> None:
            if stream_closed.is_set() or loop.is_closed():
                return
            try:
                loop.call_soon_threadsafe(stream_queue.put_nowait, (kind, payload))
            except RuntimeError as exc:
                if "closed" in str(exc).lower():
                    stream_closed.set()
                    return
                raise

        def worker() -> None:
            try:
                put_from_worker(
                    "done",
                    self._collect_content_blocks(
                        session,
                        claude_messages,
                        on_chunk=lambda chunk: put_from_worker("chunk", chunk),
                    ),
                )
            except BaseException as exc:
                put_from_worker("error", exc)

        threading.Thread(target=worker, daemon=True).start()

        sequence_number = 0

        def next_sequence() -> int:
            nonlocal sequence_number
            current = sequence_number
            sequence_number += 1
            return current

        initial_response = Response(
            id=FAKE_RESPONSES_ID,
            created_at=time.time(),
            completed_at=None,
            model=self.variant["model"],
            object="response",
            output=[],
            parallel_tool_calls=False,
            tool_choice="auto" if converted_tools else "none",
            tools=[],
            usage=self._zero_response_usage(),
            status="in_progress",
        )
        yield ResponseCreatedEvent(
            response=initial_response,
            type="response.created",
            sequence_number=next_sequence(),
        )

        streamed_text = ""
        message_started = False
        content_blocks: list[dict[str, Any]] = []

        try:
            while True:
                kind, payload = await stream_queue.get()
                if kind == "chunk":
                    delta_text = str(payload or "")
                    if not delta_text:
                        continue
                    if not message_started:
                        message_started = True
                        yield ResponseOutputItemAddedEvent(
                            item=ResponseOutputMessage(
                                id=FAKE_RESPONSES_ID,
                                content=[],
                                role="assistant",
                                type="message",
                                status="in_progress",
                            ),
                            output_index=0,
                            type="response.output_item.added",
                            sequence_number=next_sequence(),
                        )
                        yield ResponseContentPartAddedEvent(
                            content_index=0,
                            item_id=FAKE_RESPONSES_ID,
                            output_index=0,
                            part=ResponseOutputText(
                                text="",
                                type="output_text",
                                annotations=[],
                                logprobs=[],
                            ),
                            type="response.content_part.added",
                            sequence_number=next_sequence(),
                        )
                    streamed_text += delta_text
                    yield ResponseTextDeltaEvent(
                        content_index=0,
                        delta=delta_text,
                        item_id=FAKE_RESPONSES_ID,
                        logprobs=[],
                        output_index=0,
                        type="response.output_text.delta",
                        sequence_number=next_sequence(),
                    )
                    continue

                if kind == "done":
                    content_blocks = cast(list[dict[str, Any]], payload)
                    break

                raise cast(BaseException, payload)
        finally:
            stream_closed.set()

        output_items = self._content_blocks_to_output_items(content_blocks)
        first_item = output_items[0] if output_items else None
        first_is_message = isinstance(first_item, ResponseOutputMessage)

        if first_is_message:
            message_item = cast(ResponseOutputMessage, first_item)
            message_text = "".join(
                part.text for part in message_item.content if isinstance(part, ResponseOutputText)
            )
            if message_text and not message_started:
                yield ResponseOutputItemAddedEvent(
                    item=ResponseOutputMessage(
                        id=FAKE_RESPONSES_ID,
                        content=[],
                        role="assistant",
                        type="message",
                        status="in_progress",
                    ),
                    output_index=0,
                    type="response.output_item.added",
                    sequence_number=next_sequence(),
                )
                yield ResponseContentPartAddedEvent(
                    content_index=0,
                    item_id=FAKE_RESPONSES_ID,
                    output_index=0,
                    part=ResponseOutputText(
                        text="",
                        type="output_text",
                        annotations=[],
                        logprobs=[],
                    ),
                    type="response.content_part.added",
                    sequence_number=next_sequence(),
                )
                yield ResponseTextDeltaEvent(
                    content_index=0,
                    delta=message_text,
                    item_id=FAKE_RESPONSES_ID,
                    logprobs=[],
                    output_index=0,
                    type="response.output_text.delta",
                    sequence_number=next_sequence(),
                )
                message_started = True
                streamed_text = message_text

            if message_started and message_item.content:
                final_text_part = cast(ResponseOutputText, message_item.content[0])
                yield ResponseTextDoneEvent(
                    content_index=0,
                    item_id=FAKE_RESPONSES_ID,
                    logprobs=final_text_part.logprobs or [],
                    output_index=0,
                    sequence_number=next_sequence(),
                    text=final_text_part.text,
                    type="response.output_text.done",
                )
                yield ResponseContentPartDoneEvent(
                    content_index=0,
                    item_id=FAKE_RESPONSES_ID,
                    output_index=0,
                    part=final_text_part,
                    type="response.content_part.done",
                    sequence_number=next_sequence(),
                )
            yield ResponseOutputItemDoneEvent(
                item=message_item,
                output_index=0,
                type="response.output_item.done",
                sequence_number=next_sequence(),
            )

        tool_output_start = 1 if first_is_message else 0
        for idx, item in enumerate(output_items[tool_output_start:], start=tool_output_start):
            yield ResponseOutputItemDoneEvent(
                item=item,
                output_index=idx,
                type="response.output_item.done",
                sequence_number=next_sequence(),
            )

        final_response = Response(
            id=FAKE_RESPONSES_ID,
            created_at=initial_response.created_at,
            completed_at=time.time(),
            model=self.variant["model"],
            object="response",
            output=output_items,
            parallel_tool_calls=False,
            tool_choice="auto" if converted_tools else "none",
            tools=[],
            usage=self._zero_response_usage(),
            status="completed",
        )
        yield ResponseCompletedEvent(
            response=final_response,
            type="response.completed",
            sequence_number=next_sequence(),
        )


class OpenAIOrchestratedAgent:
    backend_kind = "openai-agents"
    backend_display_name = "openai-agents"
    supports_tool_reinject = False

    def __init__(self) -> None:
        os.makedirs(os.path.join(SCRIPT_DIR, "temp"), exist_ok=True)
        self.task_dir: str | None = None
        self.history: list[str] = []
        self.input_items: list[dict[str, str]] = []
        self.task_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.is_running = False
        self.stop_sig = False
        self._user_abort_requested = False
        self.verbose = True
        self.startup_error: str | None = None
        self.ready = False
        self._active_loop: asyncio.AbstractEventLoop | None = None
        self._active_task: asyncio.Task[Any] | None = None
        self._active_stream_result: Any | None = None
        self._turn_end_hooks: dict[str, Any] = {}
        self._classic_executor: Any | None = None

        self.variants = _resolve_model_variants()
        self.supports_llm_switch = len(self.variants) > 1
        self.llm_no = 0
        self.llmclient = _CompatLLMClient() if self.variants else None

        if not self.variants:
            self.startup_error = (
                "新版后端没有找到可用的模型配置。"
                "我现在会优先读取 GenericAgent 的 `mykey.py` / `mykey.json`，"
                "以及 `~/.claude/settings.json` 里的 `ANTHROPIC_*` 或 `OPENAI_*`。"
            )
            return

        try:
            _ensure_openai_agents_on_path()
            from agents import set_tracing_disabled

            set_tracing_disabled(disabled=True)
        except Exception as e:
            self.startup_error = f"新版后端未能导入 openai-agents 依赖。详情: {e}"
            return

        self._apply_variant(0)
        try:
            self._init_classic_executor()
        except Exception as e:
            self.startup_error = f"鏂扮増鍚庣鏈兘鍚姩经典 GenericAgent 执行器。详情: {e}"
            return
        self.ready = True

    def _current_variant(self) -> dict[str, Any]:
        return self.variants[self.llm_no]

    def _build_model(self) -> GenericAgentSDKModel:
        return GenericAgentSDKModel(self._current_variant())

    def _apply_variant(self, idx: int) -> None:
        variant = self.variants[idx]
        self.llm_no = idx
        self.model_name = variant["model"]
        self._variant_label = variant["label"]
        self._variant_backend_kind = variant["backend_kind"]
        os.environ["OPENAI_MODEL"] = self.model_name

        if variant["backend_kind"] == "native_claude":
            os.environ["ANTHROPIC_AUTH_TOKEN"] = variant["api_key"]
            os.environ["ANTHROPIC_BASE_URL"] = variant["base_url"]
            os.environ["ANTHROPIC_MODEL"] = variant["model"]
        else:
            os.environ["OPENAI_API_KEY"] = variant["api_key"]
            os.environ["OPENAI_BASE_URL"] = variant["base_url"]

    def _init_classic_executor(self) -> None:
        try:
            from .agentmain import GeneraticAgent
            classic = GeneraticAgent()
            classic.verbose = self.verbose
            if classic.llmclients:
                classic.next_llm(self.llm_no % len(classic.llmclients))
            threading.Thread(target=classic.run, daemon=True).start()
            self._classic_executor = classic
        except Exception as e:
            import traceback
            print(f"[Executor Init] FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()
            self._classic_executor = None

    def _reset_classic_executor(self) -> None:
        classic = self._classic_executor
        if classic is None:
            return
        classic.history = []
        classic.handler = None
        classic.stop_sig = False
        for llmclient in getattr(classic, "llmclients", []):
            try:
                llmclient.backend.history = []
                llmclient.last_tools = ""
            except Exception:
                pass

    def _run_classic_executor_task(self, user_request: str, execution_plan: str, on_progress=None) -> str:
        try:
            classic = self._classic_executor
            if classic is None:
                return "[Executor Error] Classic GenericAgent executor is unavailable. Check _init_classic_executor logs."
            prompt = (
                "You are the execution engine inside a multi-agent workflow.\n"
                "Execute the task with your normal GenericAgent tools and internal loop.\n"
                "Focus on doing the work, not re-routing or re-explaining the workflow.\n"
                "When you finish, provide a concise execution report with actions taken, evidence gathered, and remaining gaps.\n\n"
                f"Original user request:\n{user_request}\n\n"
                f"Execution plan or corrective follow-up:\n{execution_plan}"
            )
            dq = classic.put_task(prompt, source="user")
            final_output = ""
            first_progress = True
            deadline = time.time() + 900
            while True:
                if self.stop_sig:
                    classic.abort()
                    return "[Executor Error] Execution interrupted by stop signal."
                remaining = deadline - time.time()
                if remaining <= 0:
                    classic.abort()
                    return "[Executor Error] Classic GenericAgent execution timed out (900s)."
                import queue
                try:
                    item = dq.get(timeout=min(5, remaining))
                except queue.Empty:
                    continue  # 单次超时继续等待，直到总超时
                except Exception as e:
                    return f"[Executor Error] Queue get failed: {type(e).__name__}: {e}"
                if "next" in item:
                    current = str(item.get("next") or "")
                    if current and on_progress is not None:
                        try:
                            on_progress(current, first_progress)
                        except Exception:
                            pass
                        first_progress = False
                if "done" in item:
                    final_output = str(item.get("done") or "").strip()
                    break
            if final_output:
                return final_output
            return "[Executor Error] Classic GenericAgent returned empty output."
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[Executor Error] {type(e).__name__}: {e}\n{tb}")
            return f"[Executor Error] {type(e).__name__}: {e}"

    def next_llm(self, n: int = -1) -> None:
        if not self.variants:
            return
        next_idx = ((self.llm_no + 1) if n < 0 else n) % len(self.variants)
        self._apply_variant(next_idx)
        classic = self._classic_executor
        if classic is not None and getattr(classic, "llmclients", None):
            classic.next_llm(next_idx % len(classic.llmclients))

    def list_llms(self) -> list[tuple[int, str, bool]]:
        return [
            (
                idx,
                f'{item["label"]}/{item["model"]} [{item["backend_kind"]}]',
                idx == self.llm_no,
            )
            for idx, item in enumerate(self.variants)
        ]

    def get_llm_name(self, _backend: Any | None = None) -> str:
        return f"{self._variant_label}/{self.model_name} [{self._variant_backend_kind}]"

    def restore_history(self, restored: list[str], is_input_items: bool = False) -> None:
        self.abort()
        if is_input_items:
            # 新格式：restored 已经是 input_items 列表
            self.input_items = list(restored)
            self.history = _input_items_to_history_lines(self.input_items)
        else:
            # 旧格式：lines 列表
            self.history = list(restored)
            self.input_items = _restored_lines_to_inputs(restored)
        if self.llmclient:
            self.llmclient.backend.history = list(self.input_items)
            self.llmclient.last_tools = ""

    def abort(self) -> None:
        if not self.is_running:
            return
        self.stop_sig = True
        self._user_abort_requested = True
        if self._classic_executor is not None:
            try:
                self._classic_executor.abort()
            except Exception:
                pass
        if self._active_loop is not None:
            try:
                if self._active_stream_result is not None:
                    stream_result = self._active_stream_result
                    self._active_loop.call_soon_threadsafe(
                        lambda: stream_result.cancel(mode="immediate")
                    )
                if self._active_task is not None:
                    self._active_loop.call_soon_threadsafe(self._active_task.cancel)
            except Exception:
                pass

    def put_task(self, query: str, source: str = "user", images: list[str] | None = None):
        display_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.task_queue.put(
            {"query": query, "source": source, "images": images or [], "output": display_queue}
        )
        return display_queue

    def _handle_slash_cmd(self, raw_query: str, display_queue: queue.Queue[dict[str, Any]]):
        cmd = raw_query.strip()
        if not cmd.startswith("/"):
            return raw_query
        if cmd == "/help":
            display_queue.put(
                {
                    "done": "/help\n/status\n/new\n/llm\n/llm <n>\n\n新版后端暂不支持“重新注入工具”。",
                    "source": "system",
                }
            )
            return None
        if cmd == "/status":
            display_queue.put(
                {
                    "done": (
                        f"Backend: {self.backend_display_name}\n"
                        f"LLM: {self.get_llm_name()}\n"
                        f"History items: {len(self.input_items)}"
                    ),
                    "source": "system",
                }
            )
            return None
        if cmd == "/new":
            self.history = []
            self.input_items = []
            self._reset_classic_executor()
            display_queue.put({"done": "已清空新版后端的会话上下文。", "source": "system"})
            return None
        if cmd == "/resume":
            return "简单看看model_responses_openai中的最近几次对话结尾部分(除了本次)，分别简单总结一下让我选择，然后你简单阅读了解情况后作为我们接下来聊天的基础"
        if cmd.startswith("/llm"):
            parts = cmd.split()
            if len(parts) == 1:
                lines = [
                    f'[{"*" if chosen else " "}] {idx}: {name}'
                    for idx, name, chosen in self.list_llms()
                ]
                display_queue.put({"done": "\n".join(lines), "source": "system"})
                return None
            try:
                self.next_llm(int(parts[1]))
                display_queue.put(
                    {"done": f"已切换到 {self.get_llm_name()}", "source": "system"}
                )
            except Exception as e:
                display_queue.put({"done": f"切换失败: {e}", "source": "system"})
            return None
        display_queue.put({"done": f"未知命令: {cmd}", "source": "system"})
        return None

    def _build_agent_graph(self, executor_progress=None) -> dict[str, Any]:
        _ensure_openai_agents_on_path()
        from agents import Agent, function_tool

        model = self._build_model()
        common = {"model": model}

        chat_agent = Agent(
            name="chat_specialist",
            handoff_description="Handle simple conversation or explanation-only requests.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle simple conversational requests that do not require tool use. "
                "If asked about tools or skills, explain that this app can delegate execution to "
                "the classic GenericAgent executor through the workflow coordinator. "
                "Be concise, helpful, and avoid inventing actions you did not take.\n\n"
                f"{_summary_protocol()}"
            ),
            **common,
        )

        # 简化架构: 合并规划、执行、验证为一个agent
        @function_tool(name_override="run_genericagent_executor")
        async def run_genericagent_executor(user_request: str, execution_plan: str) -> str:
            """Delegate execution to the classic GenericAgent runtime.

            Args:
                user_request: The original user request.
                execution_plan: The current plan or corrective follow-up to execute.
            """
            return await asyncio.to_thread(
                self._run_classic_executor_task,
                user_request,
                execution_plan,
                executor_progress,
            )

        planner_executor_agent = Agent(
            name="planner_executor",
            handoff_description="Plan, execute and verify complex tasks involving files, code, browser or multi-step work.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle complex tasks end-to-end. For any non-trivial task:\n"
                "1. FIRST create a short, actionable plan (2-5 steps)\n"
                "2. Call run_genericagent_executor to execute the plan\n"
                "3. AFTER execution, ALWAYS verify results:\n"
                "   - Did the execution achieve all goals?\n"
                "   - Is there already a usable answer or evidence?\n"
                "   - Do NOT automatically retry just because the executor mentioned connection warnings, retries, or partial progress.\n"
                "   - Only call run_genericagent_executor a second time if the first run produced no usable findings at all.\n"
                "4. End with: Plan, Execution Summary, Verification, Final Answer\n\n"
                "IMPORTANT: You have only ONE tool: run_genericagent_executor. "
                "All file/code/browser operations happen inside the executor. "
                "Do NOT try to call any other tools. Focus on planning, delegating, and verifying.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            **common,
        )

        root_agent = Agent(
            name="task_router",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You are a router. You MUST NOT call any tools directly. "
                "Your ONLY job is to transfer to the appropriate agent via handoffs. "
                "For simple chat/conversation, transfer to chat_specialist. "
                "For any task involving files, code, browser, tools, or multi-step work, transfer to planner_executor. "
                "Never try to call run_genericagent_executor or any other tool yourself."
            ),
            handoffs=[chat_agent, planner_executor_agent],
            **common,
        )
        return {
            "root": root_agent,
            "chat": chat_agent,
            "executor": planner_executor_agent,
        }

    @staticmethod
    def _tool_name_from_item(item: Any) -> str:
        raw_item = getattr(item, "raw_item", None)
        if raw_item is not None:
            name = getattr(raw_item, "name", None)
            if isinstance(name, str) and name:
                return name
            if isinstance(raw_item, dict):
                raw_name = raw_item.get("name")
                if isinstance(raw_name, str) and raw_name:
                    return raw_name
        title = getattr(item, "title", None)
        if isinstance(title, str) and title:
            return title
        description = getattr(item, "description", None)
        if isinstance(description, str) and description:
            return description
        return "tool"

    @staticmethod
    def _stage_text_for_tool(tool_name: str) -> str:
        if tool_name == "run_genericagent_executor":
            return "[阶段] 经典执行中..."
        stage_map = {
            "transfer_to_planner_executor": "[阶段] 进入规划执行...",
            "transfer_to_chat_specialist": "[阶段] 直接回答中...",
            "run_genericagent_executor": "[阶段] 执行中...",
        }
        return stage_map.get(tool_name, "")

    @staticmethod
    def _compact_event_text(value: Any, max_len: int = 600) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                text = str(value)
        text = str(text).strip()
        if not text:
            return ""
        return smart_format(text, max_str_len=max_len)

    def _progress_text_for_event(self, event: Any) -> str:
        event_type = getattr(event, "type", "")
        if event_type == "run_item_stream_event":
            event_name = getattr(event, "name", "")
            if event_name == "tool_called":
                tool_name = self._tool_name_from_item(event.item)
                return self._stage_text_for_tool(tool_name) or f"[Tool] {tool_name}"
            if event_name == "tool_output":
                text = self._compact_event_text(getattr(event.item, "output", None))
                return text if text else "[Tool output]"
            if event_name == "handoff_requested":
                target = getattr(event.item, "target_agent", None)
                target_name = getattr(target, "name", "") if target is not None else ""
                return f"[Handoff] -> {target_name}" if target_name else "[Handoff requested]"
            if event_name == "handoff_occured":
                target = getattr(event.item, "target_agent", None)
                target_name = getattr(target, "name", "") if target is not None else ""
                return f"[Handoff completed] {target_name}" if target_name else "[Handoff completed]"
        return ""

    async def _run_task_async(
        self,
        raw_query: str,
        source: str,
        display_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        _ensure_openai_agents_on_path()
        from agents import Runner
        from agents.stream_events import RawResponsesStreamEvent
        
        MAX_RETRIES = 3
        RETRY_DELAY = 2.0  # seconds
        route_target = "root"
        
        for attempt in range(MAX_RETRIES):
            full_text = ""
            last_sent_len = 0
            seen_turn = 0

            def flush_progress(*, force: bool = False) -> None:
                nonlocal last_sent_len
                if not full_text:
                    return
                if force or len(full_text) - last_sent_len >= 12:
                    display_queue.put({"next": full_text, "source": source, "turn": max(seen_turn, 0)})
                    last_sent_len = len(full_text)

            classic_progress_snapshot = ""

            def executor_progress(snapshot: str, reset: bool = False) -> None:
                nonlocal full_text, classic_progress_snapshot
                snapshot = str(snapshot or "")
                if not snapshot:
                    return
                if reset or not classic_progress_snapshot:
                    classic_progress_snapshot = snapshot
                    if full_text and not full_text.endswith("\n\n"):
                        full_text += "\n\n"
                    full_text += snapshot
                    flush_progress(force=True)
                    return
                if snapshot.startswith(classic_progress_snapshot):
                    delta = snapshot[len(classic_progress_snapshot) :]
                    classic_progress_snapshot = snapshot
                    if delta:
                        full_text += delta
                        flush_progress(force="\n" in delta or len(delta) >= 12)
                    return
                classic_progress_snapshot = snapshot
                if full_text and not full_text.endswith("\n\n"):
                    full_text += "\n\n"
                full_text += snapshot
                flush_progress(force=True)

            try:
                # 规则快速匹配层 - 在LLM路由前进行预判
                route_result = RouterRules.match(raw_query)
                route_target = route_result.target
                route_hint = None
                if route_result.target == "chat":
                    route_hint = "[ROUTER_HINT] This is a simple conversation request. Transfer to chat_specialist immediately."
                elif route_result.target == "executor":
                    route_hint = "[ROUTER_HINT] This is a task requiring file/code/browser operations. Transfer to planner_executor immediately."
            
                agents = self._build_agent_graph(executor_progress=executor_progress)
                inputs = list(self.input_items)
                working_memory = _working_memory_message(self.history)
                if working_memory:
                    inputs.append({"role": "system", "content": working_memory})
                selected_agent = agents["root"]
                if route_result.target == "chat":
                    selected_agent = agents["chat"]
                elif route_result.target == "executor":
                    selected_agent = agents["executor"]
                # 如果规则匹配命中，添加路由提示
                if route_hint and selected_agent is agents["root"]:
                    inputs.append({"role": "system", "content": route_hint})
                inputs.append({"role": "user", "content": raw_query})
                result = Runner.run_streamed(selected_agent, input=inputs, max_turns=100)
                self._active_stream_result = result

                async for event in result.stream_events():
                    if self.stop_sig:
                        result.cancel(mode="immediate")
                        raise asyncio.CancelledError()

                    while result.current_turn > seen_turn:
                        seen_turn += 1
                        if full_text and not full_text.endswith("\n\n"):
                            full_text += "\n\n"
                        full_text += f"**LLM Running (Turn {seen_turn}) ...**\n\n"
                        flush_progress(force=True)

                    if isinstance(event, RawResponsesStreamEvent):
                        raw_event = event.data
                        if getattr(raw_event, "type", "") == "response.output_text.delta":
                            delta = str(getattr(raw_event, "delta", "") or "")
                            if delta:
                                full_text += delta
                                flush_progress(force="\n" in delta)
                        continue

                    progress_text = self._progress_text_for_event(event)
                    if progress_text:
                        if full_text and not full_text.endswith("\n"):
                            full_text += "\n"
                        full_text += f"{progress_text}\n\n"
                        flush_progress(force=True)

                if result.run_loop_exception:
                    raise result.run_loop_exception

                final_output = result.final_output
                final_text = (
                    final_output if isinstance(final_output, str) else str(final_output or "")
                ).strip()
                if _should_fallback_to_classic(route_target, final_text=final_text):
                    final_text = await asyncio.to_thread(
                        self._run_classic_executor_task,
                        raw_query,
                        _classic_executor_plan(f"Unusable orchestration output: {final_text or '[empty]'}"),
                    )
                    full_text = _inject_turn_markers(final_text)
                    seen_turn = max(1, full_text.count("LLM Running (Turn"))
                if not full_text.strip():
                    full_text = _inject_turn_markers(final_text or "[Empty response]")
                elif final_text and final_text not in full_text:
                    if seen_turn == 0:
                        full_text = _inject_turn_markers(final_text)
                        seen_turn = max(1, full_text.count("LLM Running (Turn"))
                    else:
                        if not full_text.endswith("\n\n"):
                            full_text += "\n\n"
                        full_text += final_text

                self.input_items = result.to_input_list(mode="normalized")
                if self.llmclient:
                    self.llmclient.backend.history = list(self.input_items)
                user_line = smart_format(raw_query.replace("\n", " "), max_str_len=200)
                agent_line = _extract_summary_line(final_text) or smart_format(final_text.replace("\n", " "), max_str_len=300)
                self.history.append(f"[USER]: {user_line}")
                self.history.append(f"[Agent] {agent_line}")
                _log_exchange(raw_query, full_text, self.input_items)

                for hook in self._turn_end_hooks.values():
                    try:
                        hook(
                            {
                                "turn": max(seen_turn, full_text.count("LLM Running (Turn")),
                                "summary": agent_line,
                                "exit_reason": {"result": "DONE"},
                            }
                        )
                    except Exception:
                        pass
                # 发送done信号通知前端流结束
                display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})
                return  # 成功完成，退出重试循环

            except (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError) as e:
                # 超时/连接错误 - 自动重试
                error_name = type(e).__name__
                if attempt < MAX_RETRIES - 1:
                    retry_msg = f"[WARN] {error_name}: {e}. Retrying in {RETRY_DELAY}s... (attempt {attempt + 2}/{MAX_RETRIES})"
                    print(retry_msg)
                    display_queue.put({"next": f"\n**{retry_msg}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                    await asyncio.sleep(RETRY_DELAY)
                    RETRY_DELAY *= 1.5  # 指数退避
                    continue
                else:
                    # 重试次数用尽
                    error_msg = f"[ERROR] {error_name}: {e}. All {MAX_RETRIES} retries failed."
                    print(error_msg)
                    display_queue.put({"done": f"\n**{error_msg}**\n\n请尝试重新发送请求。", "source": "system", "turn": max(seen_turn, 0)})
                    return
            except asyncio.CancelledError:
                if self._user_abort_requested or self.stop_sig:
                    display_queue.put({"done": full_text + "\n\n[已取消]", "source": "system", "turn": max(seen_turn, 0)})
                    return
                warn_msg = "[WARN] Unexpected internal cancellation."
                if attempt < MAX_RETRIES - 1:
                    print(warn_msg)
                    display_queue.put({"next": f"\n**{warn_msg} Retrying...**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                    await asyncio.sleep(RETRY_DELAY)
                    RETRY_DELAY *= 1.5
                    continue
                display_queue.put({"done": full_text or f"\n**{warn_msg}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                return
            except Exception as e:
                if _should_fallback_to_classic(route_target, exc=e):
                    fallback_text = await asyncio.to_thread(
                        self._run_classic_executor_task,
                        raw_query,
                        _classic_executor_plan(f"{type(e).__name__}: {e}"),
                    )
                    fallback_text = (fallback_text or "").strip()
                    if fallback_text:
                        full_text = _inject_turn_markers(fallback_text)
                        user_line = smart_format(raw_query.replace("\n", " "), max_str_len=200)
                        agent_line = _extract_summary_line(fallback_text) or smart_format(
                            fallback_text.replace("\n", " "), max_str_len=300
                        )
                        self.history.append(f"[USER]: {user_line}")
                        self.history.append(f"[Agent] {agent_line}")
                        _log_exchange(raw_query, full_text, self.input_items)
                        display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})
                        return
                # 其他异常 - 直接报错
                import traceback
                traceback.print_exc()
                display_queue.put({"done": f"\n**[ERROR] {type(e).__name__}: {e}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                return
            finally:
                self._active_stream_result = None

        # 不应该到达这里
        display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})

    def _drain_task(
        self,
        raw_query: str,
        source: str,
        display_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        loop = asyncio.new_event_loop()
        self._active_loop = loop
        asyncio.set_event_loop(loop)
        task = loop.create_task(self._run_task_async(raw_query, source, display_queue))
        self._active_task = task
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            display_queue.put({"done": "[Interrupted]", "source": source})
        finally:
            self._active_stream_result = None
            self._active_task = None
            self._active_loop = None
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            loop.close()

    def run(self) -> None:
        while True:
            task = self.task_queue.get()
            raw_query = task["query"]
            source = task["source"]
            display_queue = task["output"]
            raw_query = self._handle_slash_cmd(raw_query, display_queue)
            if raw_query is None:
                self.task_queue.task_done()
                continue

            self.is_running = True
            self.stop_sig = False
            self._user_abort_requested = False
            try:
                self._drain_task(raw_query, source, display_queue)
            except Exception as e:
                display_queue.put(
                    {
                        "done": f"[OpenAI Agents Error]\n\n```\n{format_error(e)}\n```",
                        "source": source,
                    }
                )
            finally:
                self.is_running = False
                self.stop_sig = False
                self._user_abort_requested = False
                self.task_queue.task_done()


def _run_task_mode(agent: OpenAIOrchestratedAgent, args: argparse.Namespace) -> None:
    threading.Thread(target=agent.run, daemon=True).start()
    task_dir = os.path.join(SCRIPT_DIR, f"temp/{args.task}")
    agent.task_dir = task_dir
    os.makedirs(task_dir, exist_ok=True)
    infile = os.path.join(task_dir, "input.txt")
    if args.input:
        with open(infile, "w", encoding="utf-8") as f:
            f.write(args.input)
    with open(infile, encoding="utf-8") as f:
        raw = f.read()
    round_no: str | int = ""
    while True:
        dq = agent.put_task(raw, source="task")
        item = dq.get(timeout=240)
        while "done" not in item:
            if "next" in item and random.random() < 0.95:
                with open(
                    os.path.join(task_dir, f"output{round_no}.txt"),
                    "w",
                    encoding="utf-8",
                ) as f:
                    f.write(item.get("next", ""))
            item = dq.get(timeout=240)
        with open(
            os.path.join(task_dir, f"output{round_no}.txt"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(item["done"] + "\n\n[ROUND END]\n")
        consume_file(task_dir, "_stop")
        for _ in range(300):
            time.sleep(2)
            raw = consume_file(task_dir, "reply.txt")
            if raw:
                break
        else:
            break
        round_no = round_no + 1 if isinstance(round_no, int) else 1


def _run_reflect_mode(agent: OpenAIOrchestratedAgent, args: argparse.Namespace) -> None:
    threading.Thread(target=agent.run, daemon=True).start()
    spec = importlib.util.spec_from_file_location("reflect_script", args.reflect)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load reflect script: {args.reflect}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mtime = os.path.getmtime(args.reflect)
    while True:
        if os.path.getmtime(args.reflect) != mtime:
            spec.loader.exec_module(mod)
            mtime = os.path.getmtime(args.reflect)
        time.sleep(getattr(mod, "INTERVAL", 5))
        task = mod.check()
        if task is None:
            continue
        dq = agent.put_task(task, source="reflect")
        item = dq.get(timeout=240)
        while "done" not in item:
            item = dq.get(timeout=240)
        result = item["done"]
        log_dir = os.path.join(SCRIPT_DIR, "temp", "reflect_logs")
        os.makedirs(log_dir, exist_ok=True)
        script_name = os.path.splitext(os.path.basename(args.reflect))[0]
        with open(
            os.path.join(log_dir, f"{script_name}_{datetime.now():%Y-%m-%d}.log"),
            "a",
            encoding="utf-8",
        ) as f:
            f.write(f"[{datetime.now():%m-%d %H:%M}]\n{result}\n\n")
        on_done = getattr(mod, "on_done", None)
        if on_done:
            on_done(result)
        if getattr(mod, "ONCE", False):
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", metavar="IODIR", help="Single task mode with file IO.")
    parser.add_argument("--reflect", metavar="SCRIPT", help="Reflect mode loader.")
    parser.add_argument("--input", help="Prompt text.")
    parser.add_argument("--llm_no", type=int, default=0)
    parser.add_argument("--bg", action="store_true", help="Spawn in background and print PID.")
    args = parser.parse_args()

    if args.bg:
        cmd = [sys.executable, "-m", "core.openai_agentmain"] + [a for a in sys.argv[1:] if a != "--bg"]
        task_dir = os.path.join(SCRIPT_DIR, f"temp/{args.task or 'openai_agent'}")
        os.makedirs(task_dir, exist_ok=True)
        proc = subprocess.Popen(
            cmd,
            cwd=SCRIPT_DIR,
            stdout=open(os.path.join(task_dir, "stdout.log"), "w", encoding="utf-8"),
            stderr=open(os.path.join(task_dir, "stderr.log"), "w", encoding="utf-8"),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print(proc.pid)
        sys.exit(0)

    agent = OpenAIOrchestratedAgent()
    if agent.startup_error:
        raise RuntimeError(agent.startup_error)
    agent.next_llm(args.llm_no)

    if args.task:
        _run_task_mode(agent, args)
    elif args.reflect:
        _run_reflect_mode(agent, args)
    else:
        threading.Thread(target=agent.run, daemon=True).start()
        while True:
            query = input("> ").strip()
            if not query:
                continue
            try:
                dq = agent.put_task(query, source="user")
                while True:
                    item = dq.get()
                    if "next" in item:
                        print(item["next"], end="", flush=True)
                    if "done" in item:
                        print(item["done"])
                        break
            except KeyboardInterrupt:
                agent.abort()
                print("\n[Interrupted]")
