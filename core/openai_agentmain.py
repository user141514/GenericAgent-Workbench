from __future__ import annotations

import argparse
import asyncio

from core.protocol.agent import AgentBackend
from core.protocol.input import AgentInput
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
import uuid
from contextlib import nullcontext
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlparse

from .router_rules import RouterRules, RouteResult
from .quality import (
    answer_quality_enabled,
    build_answer_quality_context,
    build_problem_framing_context,
    problem_framing_enabled,
    should_inject_answer_quality_context,
    should_inject_problem_framing,
)
from .runtime import (
    RuntimeProfiler,
    build_profile_path,
    build_read_prefetch_context,
    detect_read_prefetch,
    format_profile_summary,
    is_read_prefetch_enabled,
    profiling_enabled,
    safe_read_prefetch_content,
)
from .runtime.tool_contract import (
    ToolContract,
    build_orchestrator_tool_contract,
    sanitize_runtime_tool_mentions,
    synthetic_handoff_tool_name,
    validate_visible_tools,
)
from .skills import (
    build_optional_sop_context,
    build_skill_activation,
    export_skill_activation,
    skill_sop_enabled,
)

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

# Load .env file for API key configuration (preferred over mykey.py)
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass
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
    "2. <summary> 必须极简且事实化：写上次结果的新事实或当前已知状态 + 本次意图，禁止“继续处理/准备下一步”这类空话。\n"
    "3. 再输出正文；不要省略 summary。"
)
SUMMARY_PROTOCOL_EN = (
    "### Action Protocol (always in effect)\n"
    "1. Before every handoff, tool call, or final answer, emit one line of <summary>...</summary>.\n"
    "2. The <summary> must be minimal and factual: last grounded fact or current state + current intent. No filler like 'continue working'.\n"
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


ORCHESTRATOR_TOOL_CONTRACT = build_orchestrator_tool_contract()
ORCHESTRATOR_CONTEXT_AGENTS = {"planner_executor", "task_router"}
EXECUTOR_ROUTE_TARGETS = {"executor", "code", "review", "research"}


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


def _build_context_runtime(
    raw_query: str = "",
    route: str | None = None,
    project_root: str | None = None,
    profiler=None,
) -> str:
    """Build and optionally inject a Context Packet for the current task.

    Gated by GA_CONTEXT_RUNTIME_ENABLED and GA_CONTEXT_RUNTIME_MODE.
    Chat route always returns empty string.
    Preview mode writes JSON to disk, does NOT inject.
    Inject mode returns the serialized packet for injection.
    """
    import os as _os
    import json as _json
    import time as _time

    enabled = _os.environ.get("GA_CONTEXT_RUNTIME_ENABLED", "0") == "1"
    if not enabled:
        return ""

    mode = _os.environ.get("GA_CONTEXT_RUNTIME_MODE", "preview")
    if mode == "off":
        return ""

    # Chat route never gets context
    if not route or route == "chat":
        return ""

    try:
        from core.context.workspace_probe import WorkspaceProbe
        from core.context.project_identity import detect_project
        from core.context.runtime_identity import detect_runtime
        from core.context.memory_reader import MemoryReader
        from core.context.context_builder import ContextBuilder

        max_chars = int(_os.environ.get("GA_CONTEXT_PACKET_MAX_CHARS", "4000"))
        resolved_root = project_root or _os.path.abspath(
            _os.path.join(_os.path.dirname(__file__), "..")
        )

        snap = WorkspaceProbe.probe()
        pid = detect_project(snap.git_root) if snap and snap.git_root else detect_project(resolved_root)
        rt = detect_runtime(agent_backend="openai-agents")
        reader = MemoryReader(project_root=resolved_root)
        bundle = reader.scoped_query(raw_query or "", max_chars=2000)

        builder = ContextBuilder(max_chars=max_chars, policy_mode=mode)
        packet = builder.build(
            workspace=snap,
            project=pid,
            runtime=rt,
            memory_bundle=bundle,
            target_route=route,
        )

        if packet is None:
            return ""

        # Write preview JSON in all modes except off
        preview_dir = _os.environ.get(
            "GA_CONTEXT_PREVIEW_DIR",
            _os.path.join(resolved_root, "temp", "context_previews"),
        )
        _os.makedirs(preview_dir, exist_ok=True)
        run_id = _os.environ.get("GA_PROFILE_RUN_ID", "") or f"ctx_{int(_time.time())}"
        preview_path = _os.path.join(preview_dir, f"{run_id}.json")
        try:
            preview_data = {
                "generated_at": packet.generated_at,
                "target_route": packet.target_route,
                "policy_mode": packet.policy_mode,
                "total_chars": packet.total_chars,
                "source_breakdown": packet.source_breakdown,
                "workspace_cwd": packet.workspace.cwd if packet.workspace else None,
                "project_id": packet.project.project_id if packet.project else None,
                "project_name": packet.project.project_name if packet.project else None,
                "session_id": packet.runtime.session_id if packet.runtime else None,
            }
            with open(preview_path, "w", encoding="utf-8") as f:
                _json.dump(preview_data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        if mode == "preview":
            return ""  # preview: log only, no injection

        # Inject mode
        return builder.serialize(packet)

    except Exception:
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
    # Targets that use the classic executor as their backend — all are eligible
    # for fallback if the orchestrated run fails.
    _executor_targets = {"executor", "code", "review", "research"}
    if exc is not None:
        msg = f"{type(exc).__name__}: {exc}".lower()
        if "run_genericagent_executor" in msg or "not found in agent chat_specialist" in msg:
            return True
        if route_target not in _executor_targets:
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
    if route_target not in _executor_targets:
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


def _converted_tool_name(tool_schema: Any) -> str:
    if isinstance(tool_schema, dict):
        function = tool_schema.get("function")
        if isinstance(function, dict):
            return str(function.get("name") or "").strip()
        return str(tool_schema.get("name") or "").strip()
    return str(getattr(tool_schema, "name", "") or "").strip()


def _tool_contract_error_text(tool_name: str, contract: ToolContract) -> str:
    available_tools = sorted(contract.executable_tools)
    lines = [
        "Tool contract error:",
        f"`{tool_name}` is not executable in this runtime.",
        "Use one of the available tools:",
    ]
    for available_tool in available_tools:
        lines.append(f"- {available_tool}")
    lines.append("or continue with normal planner reasoning.")
    return "\n".join(lines)


def _sanitize_runtime_injected_text(text: str) -> str:
    return sanitize_runtime_tool_mentions(text, ORCHESTRATOR_TOOL_CONTRACT)


def _ensure_openai_agents_on_path() -> None:
    # Only check once; the path doesn't change during a process lifetime.
    if getattr(_ensure_openai_agents_on_path, "_done", False):
        return
    _ensure_openai_agents_on_path._done = True

    repo_src = os.path.join(os.path.dirname(SCRIPT_DIR), "openai-agents-python", "src")
    if os.path.isdir(repo_src) and repo_src not in sys.path:
        sys.path.insert(0, repo_src)
        return

    # Try alternative locations
    alt_paths = [
        os.path.join(SCRIPT_DIR, "..", "openai-agents-python", "src"),
        os.path.join(os.path.expanduser("~"), "openai-agents-python", "src"),
    ]
    for alt in alt_paths:
        alt = os.path.normpath(alt)
        if os.path.isdir(alt) and alt not in sys.path:
            sys.path.insert(0, alt)
            return


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

    # Fall back to environment variables (preferred new approach)
    api_key = os.environ.get("GA_API_KEY", "").strip()
    if api_key:
        return {
            "native_oai_config": {
                "name": os.environ.get("GA_BACKEND_NAME", "env-configured"),
                "apikey": api_key,
                "apibase": os.environ.get("GA_API_BASE_URL", "https://api.deepseek.com").rstrip("/"),
                "model": os.environ.get("GA_MODEL", "deepseek-chat"),
                "stream": os.environ.get("GA_STREAM", "true").lower() != "false",
                "max_retries": int(os.environ.get("GA_MAX_RETRIES", "3")),
                "connect_timeout": int(os.environ.get("GA_CONNECT_TIMEOUT", "10")),
                "read_timeout": int(os.environ.get("GA_READ_TIMEOUT", "120")),
            }
        }
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
    """Infer the backend protocol from configuration metadata.

    Priority (highest to lowest):
      1. Explicit `native_oai` / `native_claude` in the config key name
      2. Base URL structure (anthropic endpoint vs openai endpoint)
      3. Model name keywords with base URL context
      4. Protocol override via GA_PROTOCOL env var
    """
    lname = name.lower()
    lbase = (base_url or "").lower()
    lmodel = (model or "").lower()

    # ── Explicit backend type in config key name (highest priority) ──
    if "native_claude" in lname:
        return "native_claude"
    if "native_oai" in lname:
        return "native_oai"

    # ── Backward-compatible name heuristics ──
    # "native" + "claude" anywhere → native_claude
    if "native" in lname and "claude" in lname:
        return "native_claude"
    if "native" in lname and ("oai" in lname or "openai" in lname or "gpt" in lname):
        return "native_oai"
    # Legacy: just "claude" in name → native_claude
    if any(token in lname for token in ("claude", "anthropic")):
        return "native_claude"
    # Legacy: just "openai" / "oai" / "gpt" in name → native_oai
    if any(token in lname for token in ("oai", "openai", "gpt")):
        return "native_oai"

    # ── Base URL indicates protocol ──
    if any(token in lbase for token in ("anthropic", "/messages")):
        return "native_claude"
    if any(token in lbase for token in ("/v1", "chat/completions", "responses", "openai")):
        # OpenAI-compatible endpoint → check model to decide
        if any(token in lmodel for token in ("claude-", "claude3", "claude4", "anthropic")):
            # Claude model on OpenAI-compatible proxy → native_oai (uses OAI protocol)
            return "native_oai"
        return "native_oai"

    # ── Model name with no base URL context ──
    if any(token in lmodel for token in ("claude-", "claude3", "claude4", "anthropic")):
        # Unknown base URL but Claude model — could be either protocol
        # Default to native_oai (more widely supported by proxies)
        if lbase and not any(t in lbase for t in ("anthropic", "messages", "openai", "v1")):
            return "native_oai"
        return "native_claude"

    if any(token in lmodel for token in ("deepseek",)):
        return "native_oai"
    if any(token in lmodel for token in ("gpt-", "o1", "o3", "o4")):
        return "native_oai"

    # ── Protocol override via environment ──
    protocol_override = os.environ.get("GA_PROTOCOL", "").strip().lower()
    if protocol_override == "claude":
        return "native_claude"
    if protocol_override == "openai":
        return "native_oai"

    # ── Fallback ──
    if lbase and any(t in lbase for t in ("claude", "api.anthropic")):
        return "native_claude"

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


def _normalize_model_identity(model: str | None) -> str:
    text = str(model or "").strip().lower()
    if not text:
        return ""
    return text.replace("[1m]", "").strip()


def _normalized_backend_base_url(backend_kind: str | None, base_url: str | None) -> str:
    kind = str(backend_kind or "").strip().lower()
    if kind == "native_oai":
        return str(_normalize_openai_base_url(base_url) or "").strip().lower()
    return str(_strip_url(base_url) or "").strip().lower()


def _normalized_url_host(base_url: str | None) -> str:
    normalized = str(_strip_url(base_url) or "").strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.netloc:
        return parsed.netloc.lower()
    if "://" in normalized:
        normalized = normalized.split("://", 1)[1]
    return normalized.split("/", 1)[0].lower()


def _describe_variant_backend(variant: dict[str, Any]) -> dict[str, Any]:
    backend_kind = str(variant.get("backend_kind") or "").strip().lower()
    base_url = variant.get("base_url")
    return {
        "backend_kind": backend_kind,
        "base_url": _normalized_backend_base_url(backend_kind, base_url),
        "host": _normalized_url_host(base_url),
        "model": _normalize_model_identity(variant.get("model")),
        "api_key": str(variant.get("api_key") or "").strip(),
        "source": str(variant.get("source") or "").strip().lower(),
        "label": str(variant.get("label") or "").strip().lower(),
    }


def _describe_classic_backend(llmclient: Any, index: int) -> dict[str, Any]:
    backend = getattr(llmclient, "backend", None)
    class_name = type(backend).__name__ if backend is not None else ""
    base_url = getattr(backend, "api_base", None)
    model = getattr(backend, "model", None)
    backend_name = getattr(backend, "name", None)
    backend_kind = (
        _infer_backend_kind(class_name, base_url, model)
        or _infer_backend_kind(str(backend_name or ""), base_url, model)
        or ""
    )
    return {
        "index": index,
        "backend_kind": backend_kind,
        "base_url": _normalized_backend_base_url(backend_kind, base_url),
        "host": _normalized_url_host(base_url),
        "model": _normalize_model_identity(model),
        "api_key": str(getattr(backend, "api_key", "") or "").strip(),
        "label": str(backend_name or "").strip().lower(),
    }


def _score_variant_to_classic_backend(variant: dict[str, Any], classic_info: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    variant_info = _describe_variant_backend(variant)
    same_kind = bool(variant_info["backend_kind"] and variant_info["backend_kind"] == classic_info["backend_kind"])
    same_model = bool(variant_info["model"] and variant_info["model"] == classic_info["model"])
    same_base = bool(variant_info["base_url"] and variant_info["base_url"] == classic_info["base_url"])
    same_host = bool(variant_info["host"] and variant_info["host"] == classic_info["host"])
    same_key = bool(variant_info["api_key"] and variant_info["api_key"] == classic_info["api_key"])
    source_is_mykey = variant_info["source"] == "mykey.py"

    score = 0
    if same_kind and same_base and same_model:
        score += 100
    elif same_base and same_model:
        score += 90
    elif same_model and same_host:
        score += 75
    elif same_model:
        score += 60
    elif same_host and same_kind:
        score += 45
    elif same_host:
        score += 35
    elif same_kind:
        score += 20
    if same_key:
        score += 5

    return (
        score,
        1 if same_kind else 0,
        1 if same_model else 0,
        1 if same_base else 0,
        1 if source_is_mykey else 0,
        -int(classic_info.get("index", 0)),
    )


def _looks_like_backend_unavailable(output: str) -> bool:
    text = str(output or "").strip().lower()
    if not text:
        return False
    patterns = (
        "no available channel for model",
        '"code":"model_not_found"',
        "model_not_found",
        "503 server error",
        "http 503",
        "service unavailable",
        "sslerror",
        "max retries exceeded",
        "connectionerror",
        "connection aborted",
        "read timed out",
        "temporarily unavailable",
        "unexpected eof while reading",
    )
    return any(pattern in text for pattern in patterns)


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


def _profile_status_label(status: str) -> str:
    return status if status in {"success", "error", "aborted"} else "success"


def _start_manual_span(profiler: RuntimeProfiler | None, name: str, kind: str | None = None, metadata: dict[str, Any] | None = None):
    if profiler is None:
        return None
    cm = profiler.span(name, kind=kind, metadata=metadata)
    cm.__enter__()
    return cm


def _stop_manual_span(span_cm) -> None:
    if span_cm is None:
        return
    span_cm.__exit__(None, None, None)


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

            # Preserve reasoning_content as a thinking block so it is passed
            # back to the API on subsequent turns (required by DeepSeek v4).
            reasoning = message.get("reasoning_content")
            if reasoning and isinstance(reasoning, str) and reasoning.strip():
                content_blocks.insert(0, {"type": "thinking", "thinking": reasoning})

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
        self._audit_context: dict[str, Any] = {}
        self._runtime_profiler: RuntimeProfiler | None = None
        self._tool_contract: ToolContract = build_orchestrator_tool_contract()

    def update_audit_context(self, **kwargs: Any) -> None:
        current = dict(self._audit_context)
        current.update({k: v for k, v in kwargs.items() if v is not None})
        self._audit_context = current

    def _record_profiler_event(
        self,
        name: str,
        *,
        kind: str,
        metadata: dict[str, Any],
    ) -> None:
        if self._runtime_profiler is None:
            return
        try:
            self._runtime_profiler.record_event(name, kind=kind, metadata=metadata)
        except Exception:
            pass

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
        visible_tool_names = [
            _converted_tool_name(tool_schema)
            for tool_schema in converted_tools
            if _converted_tool_name(tool_schema)
        ]
        contract_report = validate_visible_tools(
            visible_tool_names,
            self._tool_contract,
        )
        if contract_report["removed_tools"]:
            self._record_profiler_event(
                "tool_contract_violation_detected",
                kind="tool",
                metadata={
                    "unknown_tools": contract_report["unknown_tools"],
                    "forbidden_tools": contract_report["forbidden_tools"],
                    "removed_tools": contract_report["removed_tools"],
                    "source": (
                        f"GenericAgentSDKModel._build_session:"
                        f"{self._audit_context.get('agent_name') or 'unknown_agent'}"
                    ),
                    "contract_source": self._tool_contract.source,
                },
            )
        allowed_visible_names = set(contract_report["valid_tools"])
        converted_tools = [
            tool_schema
            for tool_schema in converted_tools
            if _converted_tool_name(tool_schema) in allowed_visible_names
        ]

        # Auto-detect model capabilities for protocol negotiation
        from .llm_capabilities import detect_model_profile
        model_profile = detect_model_profile(cfg["model"], cfg["apibase"])

        if self.variant["backend_kind"] == "native_claude":
            session_cls = NativeClaudeSession
        else:
            session_cls = NativeOAISession if converted_tools else LLMSession

        # Override session class based on detected protocol
        # Only override when backend_kind is not explicitly native_oai —
        # native_oai means the config is an OpenAI-compatible endpoint (e.g. DeepSeek).
        # model_profile.protocol="claude" for these providers indicates the response
        # content-block format, not that they serve the /v1/messages endpoint.
        if model_profile.protocol == "claude" and self.variant.get("backend_kind") != "native_oai":
            session_cls = NativeClaudeSession
            # Auto-configure Claude-specific features
            if model_profile.supports_thinking and not cfg.get("thinking_type"):
                cfg["thinking_type"] = "enabled"
                cfg["thinking_budget_tokens"] = 16000  # Extended thinking for complex tasks

        session = session_cls(cfg)
        session.system = _sanitize_runtime_injected_text(system_instructions or "")
        session.tools = converted_tools
        session._audit_context = dict(self._audit_context)
        session._allowed_tool_names = allowed_visible_names
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

    def _content_blocks_to_output_items(
        self,
        content_blocks: list[dict[str, Any]],
        *,
        allowed_tool_names: set[str] | None = None,
    ) -> list[Any]:
        from agents.models.fake_id import FAKE_RESPONSES_ID
        from openai.types.responses import (
            ResponseFunctionToolCall,
            ResponseOutputMessage,
            ResponseOutputText,
        )

        output_items: list[Any] = []
        allowed_names = set(allowed_tool_names or set())

        # Preserve thinking blocks as reasoning items (required by DeepSeek v4
        # which demands that thinking content be passed back to the API).
        # Use plain dicts because Converter.maybe_reasoning_message() only
        # matches dict instances, not Pydantic model objects.
        for block in content_blocks:
            if block.get("type") != "thinking":
                continue
            thinking_text = str(block.get("thinking") or "")
            if thinking_text:
                output_items.append({
                    "id": FAKE_RESPONSES_ID,
                    "type": "reasoning",
                    "summary": [{"text": thinking_text, "type": "summary_text"}],
                })

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

        for block in content_blocks:
            if block.get("type") != "tool_use":
                continue
            tool_name = str(block.get("name") or "").strip()
            tool_report = validate_visible_tools([tool_name], self._tool_contract)
            tool_allowed = bool(tool_report["valid_tools"])
            if allowed_names and tool_name not in allowed_names:
                tool_allowed = False
                if tool_name not in tool_report["removed_tools"]:
                    tool_report["unknown_tools"] = [tool_name]
                    tool_report["removed_tools"] = [tool_name]
            if not tool_allowed:
                self._record_profiler_event(
                    "unknown_tool_call_denied",
                    kind="tool",
                    metadata={
                        "tool_name": tool_name,
                        "available_tools": sorted(allowed_names) or sorted(self._tool_contract.visible_tools),
                        "reason": "not_in_tool_contract",
                    },
                )
                message_parts.append(
                    ResponseOutputText(
                        text=_tool_contract_error_text(tool_name, self._tool_contract),
                        type="output_text",
                        annotations=[],
                        logprobs=[],
                    )
                )
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
                    name=tool_name,
                    type="function_call",
                    status="completed",
                )
            )

        if message_parts:
            output_items.insert(
                0,
                ResponseOutputMessage(
                    id=FAKE_RESPONSES_ID,
                    content=message_parts,
                    role="assistant",
                    type="message",
                    status="completed",
                ),
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
        # Use semantic classifier when HTTP status is present
        import re
        m = re.search(r'HTTP (\d+)', lowered)
        if m:
            status = int(m.group(1))
            from .llmcore import classify_http_error, ErrorAction
            _, act = classify_http_error(status, lowered)
            if act is ErrorAction.RETRY_BACKOFF:
                return text
            # AUTH_ERROR, MODEL_NOT_FOUND, PROTOCOL_ERROR → do NOT retry
            return None
        retry_markers = (
            "ssl",
            "eof",
            "connection_error",
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
        allowed_tool_names = set(getattr(session, "_allowed_tool_names", set()) or set())

        return {
            "output": self._content_blocks_to_output_items(
                self._collect_content_blocks(session, claude_messages),
                allowed_tool_names=allowed_tool_names,
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

        allowed_tool_names = set(getattr(session, "_allowed_tool_names", set()) or set())
        output_items = self._content_blocks_to_output_items(
            content_blocks,
            allowed_tool_names=allowed_tool_names,
        )
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


def _is_internal_user_message(item: dict) -> bool:
    """Return True if this is an internal execution-engine prompt, not a real user message."""
    content = item.get("content", "")
    if isinstance(content, str):
        if content.startswith("You are the execution engine"):
            return True
    elif isinstance(content, list):
        # content is a list of text blocks
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("text", "input_text"):
                text = block.get("text", "")
                if text.startswith("You are the execution engine"):
                    return True
    return False


def _strip_stream_artifacts(text: str) -> str:
    """Strip API streaming protocol artifacts from model output.

    Removes transport-layer XML tags that leak from Anthropic/OpenRouter
    streaming protocol (tool_call, function_results, assistant wrappers).
    Preserves meaningful content like <thinking> and <summary> blocks.
    """
    import re

    # Self-closing tool-call tags: <tool_call id="...">...</tool_call> and variants
    # Match tool_call elements with any attributes and body
    text = re.sub(r"<\s*/?\s*tool_calls?\s*[^>]*>", "", text)
    text = re.sub(r"<\s*/\s*tool_calls?\s*>", "", text)

    # Anthropic/OpenRouter streaming protocol wrappers
    # Matches: <|assistant|>, </|assistant|>, <|previous_assistant|>,
    #          <assistant>, </assistant>, <function_results>, </function_results>
    # and pipe-delimited variants: <|function_results|>, </|function_results|>
    for tag_name in ("assistant", "previous_assistant", "function_results"):
        text = re.sub(r"<\s*/\s*\|?\s*" + tag_name + r"\s*\|?\s*>", "", text)
        text = re.sub(r"<\s*\|?\s*" + tag_name + r"\s*\|?\s*>", "", text)

    # Bare XML processing instructions
    text = re.sub(r"<\?xml[^>]*\?>", "", text)

    # Clean up: collapse triple+ newlines, strip leading/trailing whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


class OpenAIOrchestratedAgent(AgentBackend):
    backend_kind = "openai-agents"
    backend_display_name = "openai-agents"
    supports_tool_reinject = False

    def __init__(self) -> None:
        os.makedirs(os.path.join(SCRIPT_DIR, "temp"), exist_ok=True)
        self.task_dir: str | None = None
        self.history: list[str] = []
        self.input_items: list[dict[str, str]] = []
        self.task_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._running = False
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
        self.active_profiler: RuntimeProfiler | None = None
        self._profile_run_id: str | None = None
        self._profile_status = "success"
        self._active_sdk_model: GenericAgentSDKModel | None = None
        self._executor_result_state: dict[str, Any] | None = None
        self._cached_agent_graph: dict[str, Any] | None = None
        self._cached_agent_graph_model_id: int | None = None
        self._run_store: Any | None = None
        self._runtime_host: Any | None = None
        self._runtime_session_id: str | None = None

        self.variants = _resolve_model_variants()
        self.supports_llm_switch = len(self.variants) > 1
        self.llm_no = 0
        self.llmclient = _CompatLLMClient() if self.variants else None

        if not self.variants:
            self.startup_error = (
                "未找到可用的模型配置。多Agent编排需要 OpenAI/Anthropic API key。"
                "请检查: (1) mykey.py 中是否有 native_claude_* 或 native_oai_* 配置; "
                "(2) ~/.claude/settings.json 中是否有 ANTHROPIC_* 或 OPENAI_* 环境变量。"
            )
            return

        try:
            _ensure_openai_agents_on_path()
            from agents import set_tracing_disabled

            set_tracing_disabled(disabled=True)
        except Exception as e:
            self.startup_error = (
                f"未安装 openai-agents SDK。请将 openai-agents-python 仓库放在 "
                f"{os.path.dirname(SCRIPT_DIR)} 目录下。详情: {e}"
            )
            return

        self._apply_variant(0)
        try:
            self._init_classic_executor()
        except Exception as e:
            self.startup_error = f"无法启动 Classic GenericAgent 执行器。详情: {e}"
            return
        self.ready = True

    def _current_variant(self) -> dict[str, Any]:
        return self.variants[self.llm_no]

    def _classic_backend_catalog(self, classic: Any | None = None) -> list[dict[str, Any]]:
        executor = self._classic_executor if classic is None else classic
        if executor is None:
            return []
        llmclients = getattr(executor, "llmclients", None) or []
        return [_describe_classic_backend(client, idx) for idx, client in enumerate(llmclients)]

    def _resolve_classic_executor_index(self, variant_idx: int | None = None, classic: Any | None = None) -> int | None:
        executor = self._classic_executor if classic is None else classic
        catalog = self._classic_backend_catalog(executor)
        if not catalog:
            return None
        target_variant_idx = self.llm_no if variant_idx is None else variant_idx
        if target_variant_idx < 0 or target_variant_idx >= len(self.variants):
            return int(catalog[0]["index"])
        variant = self.variants[target_variant_idx]
        best = max(
            catalog,
            key=lambda info: _score_variant_to_classic_backend(variant, info),
        )
        return int(best["index"])

    def _resolve_variant_index_for_classic(self, classic_idx: int) -> int | None:
        catalog = self._classic_backend_catalog()
        if classic_idx < 0 or classic_idx >= len(catalog):
            return None
        classic_info = catalog[classic_idx]
        if not self.variants:
            return None
        ranked = [
            (
                _score_variant_to_classic_backend(variant, classic_info),
                idx,
            )
            for idx, variant in enumerate(self.variants)
        ]
        best_score, best_idx = max(ranked, key=lambda item: item[0])
        if best_score[0] <= 0:
            return None
        return best_idx

    def _preferred_classic_retry_indices(self) -> list[int]:
        classic = self._classic_executor
        catalog = self._classic_backend_catalog(classic)
        if not catalog:
            return []
        current_idx = int(getattr(classic, "llm_no", 0) or 0)
        preferred = self._resolve_classic_executor_index(self.llm_no, classic)
        ordered: list[int] = []
        if preferred is not None and preferred != current_idx:
            ordered.append(preferred)
        for info in catalog:
            idx = int(info["index"])
            if idx == current_idx or idx in ordered:
                continue
            ordered.append(idx)
        return ordered

    def _sync_classic_executor_to_variant(self, variant_idx: int) -> int | None:
        classic = self._classic_executor
        if classic is None or not getattr(classic, "llmclients", None):
            return None
        target_idx = self._resolve_classic_executor_index(variant_idx, classic)
        if target_idx is None:
            return None
        if int(getattr(classic, "llm_no", -1) or -1) != target_idx:
            classic.switch_to_key(target_idx)
        return target_idx

    def sync_from_classic_key_index(self, classic_idx: int) -> str:
        if not self.variants:
            return self.get_llm_name()
        target_variant_idx = self._resolve_variant_index_for_classic(classic_idx)
        if target_variant_idx is None:
            target_variant_idx = min(max(int(classic_idx), 0), len(self.variants) - 1)
        return self.switch_to_key(target_variant_idx)

    def _build_model(self) -> GenericAgentSDKModel:
        model = GenericAgentSDKModel(self._current_variant())
        model._runtime_profiler = self.active_profiler
        model._tool_contract = ORCHESTRATOR_TOOL_CONTRACT
        return model

    def _update_model_audit_context(self, **kwargs: Any) -> None:
        if self._active_sdk_model is None:
            return
        self._active_sdk_model.update_audit_context(
            run_id=self._profile_run_id,
            flow="openai_orchestrated",
            **kwargs,
        )

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
            self._classic_executor = classic
            if classic.llmclients:
                self._sync_classic_executor_to_variant(self.llm_no)
            threading.Thread(target=classic.run, daemon=True).start()
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

    def _store_executor_result_state(self, state: dict[str, Any] | None) -> None:
        self._executor_result_state = dict(state) if isinstance(state, dict) else None

    def _consume_executor_result_state(self) -> dict[str, Any] | None:
        state = self._executor_result_state
        self._executor_result_state = None
        return dict(state) if isinstance(state, dict) else None

    @staticmethod
    def _should_skip_planner_followup(state: dict[str, Any] | None) -> bool:
        if not isinstance(state, dict):
            return False
        final_answer_text = str(state.get("final_answer_text") or "").strip()
        return (
            bool(state.get("final_answer_ready"))
            and bool(state.get("skip_planner_followup"))
            and not bool(state.get("tool_error"))
            and str(state.get("shortcut_type") or "") == "read_shortcut"
            and bool(final_answer_text)
        )

    def _run_classic_executor_task_once(
        self,
        user_request: str,
        execution_plan: str,
        on_progress=None,
        original_user_request: str | None = None,
        store: Any | None = None,
    ) -> str:
        self._store_executor_result_state(None)
        try:
            classic = self._classic_executor
            if classic is None:
                return "[Executor Error] Classic GenericAgent executor is unavailable. Check _init_classic_executor logs."
            original_request = str(original_user_request or user_request or "").strip()
            # Build workspace context if store is available.
            workspace_block = ""
            if store is not None:
                try:
                    summary = store.workspace_summary()
                except Exception:
                    summary = "(workspace unavailable)"
                workspace_block = (
                    f"\n=== SHARED WORKSPACE ===\n"
                    f"{summary}\n"
                    f"To reference an existing artifact, use its key name.\n"
                    f"To create or update an artifact, write the file and mention [artifact: <key>] in your output.\n"
                )
            # ── Short recent context for Classic handoff (P0c) ──
            recent_context_block = ""
            if os.environ.get("GENERIC_AGENT_RECENT_TURNS", "1") != "0":
                from core.context.recent_turns import build_recent_conversation_block as _build_short
                recent_context_block = _build_short(self.input_items, max_turns=3, max_chars=3000)
                if recent_context_block:
                    recent_context_block = (
                        "[RECENT CONTEXT — the conversation leading up to this handoff]\n"
                        f"{recent_context_block}\n"
                    )
            prompt = (
                "You are the execution engine inside a multi-agent workflow.\n"
                "Execute the task with your normal GenericAgent tools and internal loop.\n"
                "Focus on doing the work, not re-routing or re-explaining the workflow.\n"
                "When you finish, provide a concise execution report with actions taken, evidence gathered, and remaining gaps.\n"
                f"{workspace_block}"
                f"{recent_context_block}"
                f"Original user request:\n{original_request}\n\n"
                f"Execution plan or corrective follow-up:\n{execution_plan}"
            )
            dq = classic.put_task(prompt, source="user", run_id=self._profile_run_id)
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
                if isinstance(item, dict) and item.get("type") == "status":
                    if on_progress is not None:
                        try:
                            on_progress(item, False)
                        except Exception:
                            pass
                    continue
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
                    self._store_executor_result_state(
                        {
                            "final_answer_ready": bool(item.get("final_answer_ready")),
                            "final_answer_text": str(item.get("final_answer_text") or "").strip(),
                            "shortcut_type": str(item.get("shortcut_type") or "").strip(),
                            "skip_planner_followup": bool(item.get("skip_planner_followup")),
                            "shortcut_reason": str(item.get("shortcut_reason") or "").strip(),
                            "shortcut_confidence": item.get("shortcut_confidence"),
                            "tool_error": bool(item.get("tool_error")),
                        }
                    )
                    break
            if final_output:
                # Strip classic executor noise (LLM Running markers, tool-call
                # transcripts) before returning to the multi-agent LLM. The raw
                # format is designed for human display and confuses another LLM
                # into misinterpreting code content (e.g. exception handlers) as
                # execution errors.
                cleaned = _extract_classic_executor_report(final_output)
                return cleaned if cleaned else final_output
            return "[Executor Error] Classic GenericAgent returned empty output."
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[Executor Error] {type(e).__name__}: {e}\n{tb}")
            return f"[Executor Error] {type(e).__name__}: {e}"

    def _run_classic_executor_task(
        self,
        user_request: str,
        execution_plan: str,
        on_progress=None,
        original_user_request: str | None = None,
        store: Any | None = None,
    ) -> str:
        # ── P2-3 + P2-4: ExecutionPolicy evaluation with skill effects ──
        from .runtime.execution_policy import evaluate_operation, get_policy_mode as _get_policy_mode

        policy_mode = _get_policy_mode()
        active_policy = getattr(self, "_active_policy", None) or {}
        policy_decision = evaluate_operation(user_request, execution_plan, mode=policy_mode, policy=active_policy)
        if getattr(self, "_active_span_id", None) is not None and self.active_profiler is not None:
            self.active_profiler.record_event(
                "execution_policy_check",
                kind="policy",
                metadata={
                    "mode": policy_mode,
                    "allowed": policy_decision.allowed,
                    "risk_level": policy_decision.risk_level,
                    "matched_patterns": policy_decision.matched_patterns,
                    "reason": policy_decision.reason,
                },
            )
        if not policy_decision.allowed:
            return (
                f"[POLICY BLOCKED] ({policy_decision.mode} mode)\n"
                f"Risk level: {policy_decision.risk_level}\n"
                f"Reason: {policy_decision.reason}\n"
                f"Matched: {', '.join(policy_decision.matched_patterns[:5])}"
            )

        first_output = self._run_classic_executor_task_once(
            user_request,
            execution_plan,
            on_progress=on_progress,
            original_user_request=original_user_request,
            store=store,
        )
        if not _looks_like_backend_unavailable(first_output):
            return first_output

        classic = self._classic_executor
        if classic is None:
            return first_output

        current_idx = int(getattr(classic, "llm_no", 0) or 0)
        last_output = first_output
        for fallback_idx in self._preferred_classic_retry_indices():
            try:
                classic.switch_to_key(fallback_idx)
                self._reset_classic_executor()
            except Exception:
                continue
            if self.active_profiler is not None:
                self.active_profiler.record_event(
                    "executor_backend_retry",
                    kind="llm",
                    metadata={
                        "from_index": current_idx,
                        "to_index": fallback_idx,
                        "reason": "backend_unavailable",
                    },
                )
            retry_output = self._run_classic_executor_task_once(
                user_request,
                execution_plan,
                on_progress=on_progress,
                original_user_request=original_user_request,
                store=store,
            )
            last_output = retry_output
            if not _looks_like_backend_unavailable(retry_output):
                return retry_output
        return last_output

    def switch_to_key(self, n: int) -> str:
        """Switch directly to a specific variant index. Returns the new model name."""
        if not self.variants or n < 0 or n >= len(self.variants):
            return self.get_llm_name()
        self._apply_variant(n)
        # Invalidate agent graph cache so next task rebuilds with new model
        self._cached_agent_graph = None
        self._cached_agent_graph_model_id = None
        self._active_sdk_model = None
        self._sync_classic_executor_to_variant(n)
        return self.get_llm_name()

    def next_llm(self, n: int = -1) -> None:
        if not self.variants:
            return
        next_idx = ((self.llm_no + 1) if n < 0 else n) % len(self.variants)
        self.switch_to_key(next_idx)

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

    def get_key_labels(self) -> list[str]:
        """Return display labels for all configured variants (for UI model switcher)."""
        labels = []
        for idx, item in enumerate(self.variants):
            prefix = f"Key{idx + 1}"
            active = " *" if idx == self.llm_no else ""
            labels.append(f"{prefix}: {item['model']} [{item['backend_kind']}]{active}")
        return labels

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

    # ── AgentBackend protocol (Phase OA1) ──────────────────────────────

    @property
    def is_running(self) -> bool:
        """Whether a task is currently being processed (AgentBackend protocol)."""
        return self._running

    def submit(self, task: AgentInput):
        """Submit a task via the AgentBackend protocol.

        Returns an AgentOutputChannel for consuming streaming output.
        ``put_task()`` is the legacy equivalent; this method delegates to it.
        """
        from core.protocol.channel import QueueOutputChannel

        raw_q = self.put_task(task.query, task.source, task.images, task.run_id)
        return QueueOutputChannel.from_legacy_queue(raw_q)

    def abort(self) -> None:
        if not self._running:
            return
        self.stop_sig = True
        self._user_abort_requested = True
        runtime_host = getattr(self, "_runtime_host", None)
        if runtime_host is not None:
            try:
                runtime_host.request_stop(reason="user_abort")
            except Exception:
                pass
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

    def put_task(self, query: str, source: str = "user", images: list[str] | None = None, run_id: str | None = None):
        """Submit a task (legacy API). Prefer ``submit(AgentInput(...))`` for new code."""
        display_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.task_queue.put(
            {"query": query, "source": source, "images": images or [], "output": display_queue, "run_id": run_id}
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

    def _build_agent_graph(
        self, original_user_request: str, executor_progress=None,
        graph_mode: str = "full",
    ) -> dict[str, Any]:
        self._active_policy = None  # P2-4: reset per-run
        if graph_mode == "dynamic":
            return self._build_dynamic_graph(original_user_request, executor_progress)
        # Return cached graph if model hasn't changed since last build.
        if (
            self._cached_agent_graph is not None
            and self._cached_agent_graph_model_id == self.llm_no
        ):
            self._active_sdk_model = self._cached_agent_graph["root"].model
            return self._cached_agent_graph
        return self._build_minimal_runtime_graph(
            original_user_request,
            executor_progress=executor_progress,
            cache_graph=True,
        )

        _ensure_openai_agents_on_path()
        from agents import Agent, function_tool

        model = self._build_model()
        self._active_sdk_model = model
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

        # Shared executor tool - all specialized agents use this.
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
                original_user_request,
                getattr(self, "_run_store", None),
            )

        # ── Code Agent: writing, modifying, debugging code ──
        code_agent = Agent(
            name="code_agent",
            handoff_description="Write, modify, debug, or refactor code.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You are a code specialist. Your focus is producing correct, clean, well-structured code.\n"
                "For every code task:\n"
                "1. BRIEFLY state the approach (1-2 sentences) — do not write long plans.\n"
                "2. Call run_genericagent_executor with a clear, actionable execution plan.\n"
                "3. AFTER execution, verify:\n"
                "   - Does the code compile / run without errors?\n"
                "   - Are edge cases handled?\n"
                "   - Is the code readable and follows conventions?\n"
                "4. AFTER producing code, hand off to review_agent for review "
                "(unless the user explicitly asked to skip review).\n"
                "5. After producing code, write it to the shared workspace by instructing the executor "
                "to include [artifact: <name>] markers in its output.\n"
                "6. If the review comes back with issues, fix them and update the artifact.\n"
                "7. When you encounter an unfamiliar API or library, hand off to research_agent "
                "to look up documentation first.\n\n"
                "Quality standards:\n"
                "- Prefer tested, working code over speculative implementations.\n"
                "- Handle errors explicitly, not silently.\n"
                "- Name variables and functions clearly.\n"
                "- Keep functions small and single-purpose.\n\n"
                "IMPORTANT: You have ONE tool (run_genericagent_executor) and "
                "TWO handoffs (review_agent for code review, research_agent for documentation lookup). "
                "Use the shared workspace to store code artifacts so review_agent can access them.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            handoffs=[],  # filled after other agents are defined
            **common,
        )

        # ── Review Agent: code review, testing, security audit ──
        review_agent = Agent(
            name="review_agent",
            handoff_description="Review code, run tests, verify correctness, find bugs and security issues.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You are a code reviewer and quality specialist. Your focus is finding problems "
                "and verifying correctness.\n"
                "For every review task:\n"
                "1. Identify what needs to be checked (correctness, security, performance, tests).\n"
                "2. Call run_genericagent_executor with specific review instructions:\n"
                "   - Run existing tests first.\n"
                "   - Check for edge cases, error handling, input validation.\n"
                "   - Look for security issues (injection, leaks, race conditions).\n"
                "   - Check code style and conventions.\n"
                "3. Summarize findings clearly:\n"
                "   - Critical issues (must fix)\n"
                "   - Warnings (should fix)\n"
                "   - Suggestions (nice to have)\n"
                "4. If you find issues that need code changes, reference the artifact key from the "
                "shared workspace and hand off to code_agent with SPECIFIC fix instructions.\n"
                "5. After the code_agent returns with fixes, re-review the artifact to verify.\n"
                "6. If the code passes review, write your review report as an artifact "
                "([artifact: review-report]) and present your final approval.\n"
                "7. If you need to verify code against external documentation or specifications, "
                "hand off to research_agent first.\n\n"
                "Be specific. Point to exact lines or patterns. "
                "Do NOT just say \"looks good\" — explain WHY it looks good.\n\n"
                "IMPORTANT: You have ONE tool (run_genericagent_executor) and "
                "TWO handoffs (code_agent for fixes, research_agent for spec/doc verification). "
                "Read artifacts from the shared workspace to review code. "
                "Write review findings as artifacts.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            handoffs=[],  # filled after other agents are defined
            **common,
        )

        # ── Research Agent: information gathering, documentation, exploration ──
        research_agent = Agent(
            name="research_agent",
            handoff_description="Search information, read files and documentation, explore codebases.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You are a research specialist. Your focus is finding accurate information "
                "and presenting it clearly with sources.\n"
                "For every research task:\n"
                "1. Clarify what information is needed.\n"
                "2. Call run_genericagent_executor to:\n"
                "   - Read relevant files, documentation, or search results.\n"
                "   - Explore the codebase to find relevant code patterns.\n"
                "   - Search for API documentation and usage examples.\n"
                "3. Organize findings:\n"
                "   - Key facts with sources (file paths, URLs, line numbers).\n"
                "   - Code examples with context.\n"
                "   - Gotchas and common pitfalls.\n"
                "4. If the executor's findings are incomplete, call it again with refined search terms.\n"
                "5. Write your research findings as artifacts in the shared workspace "
                "([artifact: research-findings]) with sources and code examples.\n"
                "6. If your findings indicate that code implementation is needed, "
                "hand off to code_agent with references to the research artifacts.\n"
                "7. If you found potential issues or security concerns that need verification, "
                "hand off to review_agent.\n"
                "8. If the question can be answered with information alone (no code needed), "
                "present your findings as the final answer.\n\n"
                "Be thorough but concise. Always cite your sources. "
                "Distinguish between facts you found and your interpretation.\n\n"
                "IMPORTANT: You have ONE tool (run_genericagent_executor) and "
                "TWO handoffs (code_agent for implementation, review_agent for verification). "
                "Write research artifacts to the shared workspace. "
                "Use handoffs only when the user's intent requires follow-up action.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            handoffs=[],  # filled after other agents are defined
            **common,
        )

        # ── General Executor (backward-compatible fallback) ──
        planner_executor_agent = Agent(
            name="planner_executor",
            handoff_description="General-purpose planner and executor for complex multi-step tasks.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle complex, multi-step tasks that do not clearly fall into code-writing, "
                "code-review, or research categories.\n"
                "1. FIRST create a short, actionable plan (2-5 steps)\n"
                "2. Call run_genericagent_executor to execute the plan\n"
                "3. AFTER execution, ALWAYS verify results:\n"
                "   - Did the execution achieve all goals?\n"
                "   - Is there already a usable answer or evidence?\n"
                "   - Only retry if the first run produced no usable findings at all.\n"
                "4. End with: Plan, Execution Summary, Verification, Final Answer\n\n"
                "IMPORTANT: You have only ONE tool: run_genericagent_executor. "
                "All file/code/browser operations happen inside the executor.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            **common,
        )

        # ── Wire up cross-handoffs (Level 2: multi-hop pipelines) ──
        # Set handoffs after all agents exist so they can reference each other.
        code_agent.handoffs = [review_agent, research_agent]
        review_agent.handoffs = [code_agent, research_agent]
        research_agent.handoffs = [code_agent, review_agent]
        # planner_executor and chat_specialist remain leaf agents (no handoffs).

        root_agent = Agent(
            name="task_router",
            instructions=(
                "You are a router. You have NO tools — do not attempt to call any tools.\n"
                "Your ONLY job is to transfer to the appropriate agent via handoffs.\n"
                "- Simple chat or conversation → chat_specialist\n"
                "- Code writing, modification, debugging, refactoring → code_agent\n"
                "- Code review, testing, security audit, bug finding → review_agent\n"
                "- Information search, documentation lookup, codebase exploration → research_agent\n"
                "- Complex multi-step tasks mixing multiple concerns → planner_executor\n"
            ),
            handoffs=[chat_agent, code_agent, review_agent, research_agent, planner_executor_agent],
            **common,
        )
        graph = {
            "root": root_agent,
            "chat": chat_agent,
            "executor": planner_executor_agent,
            "code": code_agent,
            "review": review_agent,
            "research": research_agent,
        }
        self._cached_agent_graph = graph
        self._cached_agent_graph_model_id = self.llm_no
        return graph

    def _build_dynamic_graph(
        self, original_user_request: str, executor_progress=None,
    ) -> dict[str, Any]:
        """Level 3: Task→DAG compiler — build only the agents needed for this task.

        Uses RouterRules keyword counts to determine which agents to create,
        then wires the minimal handoff topology.
        """
        from core.router_rules import RouterRules

        _ensure_openai_agents_on_path()
        from agents import Agent, function_tool

        model = self._build_model()
        self._active_sdk_model = model
        common = {"model": model}

        # Analyze the query to determine needed agent types.
        query = str(original_user_request or "").strip()
        route_result = RouterRules.match(query)

        # Count per-category keyword hits to determine needed agents.
        hit_counts = RouterRules.keyword_hit_counts(query)
        code_hits = int(hit_counts.get("code", 0))
        review_hits = int(hit_counts.get("review", 0))
        research_hits = int(hit_counts.get("research", 0))
        chat_hits = int(hit_counts.get("chat", 0))
        exec_hits = int(hit_counts.get("executor", 0))

        needs_code = code_hits > 0 or (exec_hits > 0 and code_hits >= review_hits and code_hits >= research_hits)
        needs_review = review_hits > 0
        needs_research = research_hits > 0
        needs_chat = route_result.target == "chat" or (chat_hits > exec_hits and chat_hits > 0)

        # Shared executor tool
        @function_tool(name_override="run_genericagent_executor")
        async def run_genericagent_executor(user_request: str, execution_plan: str) -> str:
            return await asyncio.to_thread(
                self._run_classic_executor_task,
                user_request,
                execution_plan,
                executor_progress,
                original_user_request,
                getattr(self, "_run_store", None),
            )

        agent_map: dict[str, Any] = {}
        handoff_list: list[Any] = []
        leaf_count = 0

        # Always include chat_specialist for conversation fallback
        chat_agent = Agent(
            name="chat_specialist",
            handoff_description="Handle simple conversation or explanation-only requests.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle simple conversational requests that do not require tool use. "
                "Be concise, helpful, and avoid inventing actions you did not take.\n\n"
                f"{_summary_protocol()}"
            ),
            **common,
        )
        agent_map["chat"] = chat_agent
        handoff_list.append(chat_agent)

        # Planner executor as general fallback
        planner_executor_agent = Agent(
            name="planner_executor",
            handoff_description="General-purpose planner and executor.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle complex, multi-step tasks.\n"
                "1. Create a short, actionable plan.\n"
                "2. Call run_genericagent_executor to execute.\n"
                "3. Verify results.\n"
                "4. End with: Plan, Execution Summary, Verification, Final Answer.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            **common,
        )
        agent_map["executor"] = planner_executor_agent
        handoff_list.append(planner_executor_agent)

        # ── Create only the specialized agents needed ──

        if needs_code or (not needs_review and not needs_research and exec_hits > 0):
            code_agent = Agent(
                name="code_agent",
                handoff_description="Write, modify, debug, or refactor code.",
                instructions=(
                    f"{CAPABILITY_BRIEF} "
                    "You are a code specialist. Produce correct, clean code. "
                    "Call run_genericagent_executor to do the work. "
                    "Write artifacts to the shared workspace with [artifact: <name>].\n\n"
                    f"{_summary_protocol()}"
                ),
                tools=[run_genericagent_executor],
                handoffs=[],
                **common,
            )
            agent_map["code"] = code_agent
            handoff_list.append(code_agent)
            leaf_count += 1

        if needs_review:
            review_agent = Agent(
                name="review_agent",
                handoff_description="Review code, run tests, verify correctness.",
                instructions=(
                    f"{CAPABILITY_BRIEF} "
                    "You are a code reviewer. Find problems, verify correctness. "
                    "Call run_genericagent_executor for testing. "
                    "Read and write artifacts from the shared workspace.\n\n"
                    f"{_summary_protocol()}"
                ),
                tools=[run_genericagent_executor],
                handoffs=[],
                **common,
            )
            agent_map["review"] = review_agent
            handoff_list.append(review_agent)
            leaf_count += 1

        if needs_research:
            research_agent = Agent(
                name="research_agent",
                handoff_description="Search information, read documentation.",
                instructions=(
                    f"{CAPABILITY_BRIEF} "
                    "You are a research specialist. Find accurate information. "
                    "Call run_genericagent_executor to search and read. "
                    "Write findings as artifacts. Always cite sources.\n\n"
                    f"{_summary_protocol()}"
                ),
                tools=[run_genericagent_executor],
                handoffs=[],
                **common,
            )
            agent_map["research"] = research_agent
            handoff_list.append(research_agent)
            leaf_count += 1

        # ── Wire cross-handoffs only between agents that exist ──
        # If both code and review exist, connect them bidirectionally.
        if "code" in agent_map and "review" in agent_map:
            agent_map["code"].handoffs = [agent_map["review"]]
            agent_map["review"].handoffs = [agent_map["code"]]
            if "research" in agent_map:
                agent_map["code"].handoffs.append(agent_map["research"])
                agent_map["review"].handoffs.append(agent_map["research"])
        if "research" in agent_map:
            if "code" in agent_map and agent_map["code"] not in agent_map["research"].handoffs:
                agent_map["research"].handoffs.append(agent_map["code"])
            if "review" in agent_map and agent_map["review"] not in agent_map["research"].handoffs:
                agent_map["research"].handoffs.append(agent_map["review"])

        # ── Root agent with handoffs to all created agents ──
        agent_list_str = ", ".join(
            a.name for a in handoff_list if a.name != "task_router"
        )
        root_agent = Agent(
            name="task_router",
            instructions=(
                f"You are a router with NO tools. Transfer to the appropriate agent. "
                f"Available agents: {agent_list_str}."
            ),
            handoffs=handoff_list,
            **common,
        )
        agent_map["root"] = root_agent

        return agent_map

    # Active runtime graph override: keep the real orchestrator limited to
    # task_router -> chat_specialist/planner_executor.
    def _build_agent_graph(
        self, original_user_request: str, executor_progress=None,
        graph_mode: str = "full",
    ) -> dict[str, Any]:
        self._active_policy = None  # P2-4: reset per-run
        if graph_mode == "dynamic":
            return self._build_dynamic_graph(original_user_request, executor_progress)
        if (
            self._cached_agent_graph is not None
            and self._cached_agent_graph_model_id == self.llm_no
        ):
            self._active_sdk_model = self._cached_agent_graph["root"].model
            return self._cached_agent_graph
        return self._build_minimal_runtime_graph(
            original_user_request,
            executor_progress=executor_progress,
            cache_graph=True,
        )

    def _build_dynamic_graph(
        self, original_user_request: str, executor_progress=None,
    ) -> dict[str, Any]:
        return self._build_minimal_runtime_graph(
            original_user_request,
            executor_progress=executor_progress,
            cache_graph=False,
        )

    def _build_minimal_runtime_graph(
        self,
        original_user_request: str,
        executor_progress=None,
        *,
        cache_graph: bool,
    ) -> dict[str, Any]:
        _ensure_openai_agents_on_path()
        from agents import Agent, function_tool

        model = self._build_model()
        self._active_sdk_model = model
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

        @function_tool(name_override="run_genericagent_executor")
        async def run_genericagent_executor(user_request: str, execution_plan: str) -> str:
            """Delegate execution to the classic GenericAgent runtime."""
            return await asyncio.to_thread(
                self._run_classic_executor_task,
                user_request,
                execution_plan,
                executor_progress,
                original_user_request,
                getattr(self, "_run_store", None),
            )

        planner_executor_agent = Agent(
            name="planner_executor",
            handoff_description="General-purpose planner and executor for all non-chat tasks.",
            instructions=(
                f"{CAPABILITY_BRIEF} "
                "You handle all non-chat execution tasks in this runtime, including code, review, "
                "research, and mixed multi-step work.\n"
                "1. FIRST create a short, actionable plan (2-5 steps)\n"
                "2. Call run_genericagent_executor to execute the plan\n"
                "3. AFTER execution, ALWAYS verify results:\n"
                "   - Did the execution achieve all goals?\n"
                "   - Is there already a usable answer or evidence?\n"
                "   - Only retry if the first run produced no usable findings at all.\n"
                "4. End with: Plan, Execution Summary, Verification, Final Answer\n\n"
                "IMPORTANT: You have only ONE tool: run_genericagent_executor. "
                "All file/code/browser operations happen inside the executor.\n\n"
                f"{_summary_protocol()}"
            ),
            tools=[run_genericagent_executor],
            **common,
        )

        root_agent = Agent(
            name="task_router",
            instructions=(
                "You are a router. You have NO tools - do not attempt to call any tools.\n"
                "Your ONLY job is to transfer to the appropriate agent via handoffs.\n"
                "- Simple chat or conversation -> chat_specialist\n"
                "- Any file/code/browser/research/review/multi-step task -> planner_executor\n"
            ),
            handoffs=[chat_agent, planner_executor_agent],
            **common,
        )
        graph = {
            "root": root_agent,
            "chat": chat_agent,
            "executor": planner_executor_agent,
        }
        if cache_graph:
            self._cached_agent_graph = graph
            self._cached_agent_graph_model_id = self.llm_no
        return graph

    async def _run_parallel_tasks(
        self, subtasks: list[str], source: str,
        display_queue, profiler, executor_progress,
    ) -> str:
        """Level 3: Run independent sub-tasks in parallel via asyncio.gather.

        Each sub-task gets its own agent graph and executor invocation.
        Results are collected and merged into a single output.
        """
        from agents import Runner
        from agents.stream_events import RawResponsesStreamEvent

        async def _run_single_subtask(subtask_query: str, index: int) -> str:
            """Run one sub-task: route → build graph → run stream → collect output."""
            route = RouterRules.match(subtask_query)
            target = route.target or "executor"
            execution_mode = getattr(route, "mode", "single_agent")
            agents = self._build_agent_graph(subtask_query, executor_progress=executor_progress, graph_mode="dynamic")
            selected = agents.get("root")
            if target == "chat":
                selected = agents.get("chat", selected)
            elif execution_mode == "single_agent" and target in EXECUTOR_ROUTE_TARGETS:
                selected = agents.get("executor", selected)

            try:
                result = Runner.run_streamed(selected, input=subtask_query, max_turns=50)
                output_parts = []
                async for event in result.stream_events():
                    if isinstance(event, RawResponsesStreamEvent):
                        delta = getattr(event.data, "delta", "")
                        if delta:
                            output_parts.append(str(delta))
                return f"[Sub-task {index + 1}] {subtask_query}\n{''.join(output_parts).strip()}\n"
            except Exception as e:
                return f"[Sub-task {index + 1} ERROR] {subtask_query}: {type(e).__name__}: {e}\n"

        tasks = [_run_single_subtask(q.strip(), i) for i, q in enumerate(subtasks)]
        results = await __import__("asyncio").gather(*tasks, return_exceptions=True)

        merged = f"=== Parallel Execution: {len(subtasks)} sub-tasks ===\n\n"
        for r in results:
            merged += str(r) + "\n"
        merged += "=== End Parallel Execution ==="
        return merged

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
        profiler = self.active_profiler
        
        for attempt in range(MAX_RETRIES):
            full_text = ""
            last_sent_len = 0
            seen_turn = 0
            selected_agent_name = "root"
            active_tool_span = None
            active_tool_name = ""
            active_llm_turn_span = None
            planning_span = None
            execution_span = None
            llm_span = None
            stream_span = None
            planner_followup_override = None
            runtime_host = getattr(self, "_runtime_host", None)

            def flush_progress(*, force: bool = False) -> None:
                nonlocal last_sent_len
                if not full_text:
                    return
                if force or len(full_text) - last_sent_len >= 12:
                    display_queue.put({"next": full_text, "source": source, "turn": max(seen_turn, 0)})
                    last_sent_len = len(full_text)

            classic_progress_snapshot = ""

            def executor_progress(snapshot: Any, reset: bool = False) -> None:
                nonlocal full_text, classic_progress_snapshot
                if isinstance(snapshot, dict) and snapshot.get("type") == "status":
                    status_item = dict(snapshot)
                    status_item.setdefault("source", source)
                    status_item.setdefault("task_id", self._profile_run_id)
                    display_queue.put(status_item)
                    return
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

            def runtime_collaboration_snapshot() -> dict[str, Any] | None:
                store = getattr(self, "_run_store", None)
                snapshot_fn = getattr(store, "snapshot", None)
                if not callable(snapshot_fn):
                    return None
                try:
                    return snapshot_fn()
                except Exception:
                    return None

            def runtime_complete_active_turn() -> None:
                if runtime_host is None or seen_turn <= 0:
                    return
                try:
                    runtime_host.complete_llm_turn(
                        seen_turn,
                        selected_agent=selected_agent_name,
                        result_summary=full_text[-300:],
                    )
                except Exception:
                    pass

            def runtime_complete_active_tool(*, error: str | None = None, summary: str = "") -> None:
                nonlocal active_tool_name
                if runtime_host is None or not active_tool_name:
                    return
                try:
                    if error:
                        runtime_host.fail_tool(active_tool_name, error=error)
                    else:
                        runtime_host.complete_tool(
                            active_tool_name,
                            result_summary=summary,
                            collaboration_artifacts=runtime_collaboration_snapshot(),
                        )
                except Exception:
                    pass
                active_tool_name = ""

            def runtime_finalize_success(summary: str, *, verdict: str = "pass_with_warnings") -> None:
                if runtime_host is None:
                    return
                try:
                    runtime_host.begin_review()
                    runtime_host.complete_review(verdict=verdict, summary=summary)
                    runtime_host.complete_session(summary=summary)
                except Exception:
                    pass

            try:
                # Create a shared artifact store for this run (Level 4 blackboard).
                from core.runtime.shared_store import SharedArtifactStore
                self._run_store = SharedArtifactStore()
                if runtime_host is not None:
                    try:
                        runtime_host.sync_collaboration_store(self._run_store)
                    except Exception:
                        pass

                # 规则快速匹配层 - 在LLM路由前进行预判
                planning_span = _start_manual_span(profiler, "routing_and_planning", kind="agent", metadata={"attempt": attempt + 1, "source": source})
                if getattr(self, "_force_multi_agent", False):
                    # ── Multi-agent mode short-circuit: skip RouterRules, go direct ──
                    route_result = RouterRules.match(raw_query)  # still classify for audit
                    route_target = route_result.target
                    execution_mode = "multi_agent"
                    self._force_multi_agent = False
                else:
                    route_result = RouterRules.match(raw_query)
                    route_target = route_result.target
                    execution_mode = getattr(route_result, "mode", "single_agent")

                # ── Parallel sub-task detection (Level 3) ──
                parallel_subtasks = list(getattr(route_result, "parallel_subtasks", []) or [])
                if execution_mode == "multi_agent" and parallel_subtasks and len(parallel_subtasks) >= 2 and os.environ.get("GA_PARALLEL") == "1":
                    if runtime_host is not None:
                        try:
                            runtime_host.apply_route(
                                route_target=route_target,
                                execution_mode=execution_mode,
                                parallel_subtasks=parallel_subtasks,
                            )
                        except Exception as runtime_route_error:
                            print(f"[runtime_host] route apply failed: {runtime_route_error}")
                    full_text = await self._run_parallel_tasks(
                        parallel_subtasks, source, display_queue, profiler, executor_progress
                    )
                    runtime_finalize_success(
                        _sanitize_runtime_injected_text(
                            _extract_summary_line(full_text)
                            or smart_format(full_text.replace("\n", " "), max_str_len=300)
                        )
                    )
                    # Cleanup and exit after parallel run
                    self._run_store = None
                    self._active_stream_result = None
                    display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})
                    return

                answer_quality_flag = bool(answer_quality_enabled())
                answer_quality_query_match = should_inject_answer_quality_context(raw_query, route_target=None)
                problem_framing_flag = bool(problem_framing_enabled())
                problem_framing_query_match = should_inject_problem_framing(raw_query)
                answer_quality_route_override = (
                    answer_quality_flag
                    and answer_quality_query_match
                    and route_target != "executor"
                )
                route_hint = None
                if route_result.target == "chat":
                    route_hint = "[ROUTER_HINT] This is a simple conversation request. Transfer to chat_specialist immediately."
                elif execution_mode == "multi_agent":
                    route_hint = "[ROUTER_HINT] This request needs multi-agent collaboration. Transfer to task_router immediately."
                elif route_result.target == "code":
                    route_hint = "[ROUTER_HINT] This is a code writing/modification task. Transfer to planner_executor in single-agent mode immediately."
                elif route_result.target == "review":
                    route_hint = "[ROUTER_HINT] This is a code review/testing task. Transfer to planner_executor in single-agent mode immediately."
                elif route_result.target == "research":
                    route_hint = "[ROUTER_HINT] This is an information gathering/research task. Transfer to planner_executor in single-agent mode immediately."
                elif route_result.target == "executor":
                    route_hint = "[ROUTER_HINT] This is an execution task. Transfer to planner_executor in single-agent mode immediately."
                if answer_quality_route_override:
                    route_target = "executor"
                    execution_mode = "single_agent"
                    route_hint = "[ROUTER_HINT] This is a roadmap / architecture / capability-planning request. Transfer to planner_executor in single-agent mode immediately."
                if runtime_host is not None:
                    try:
                        runtime_host.apply_route(
                            route_target=route_target,
                            execution_mode=execution_mode,
                            parallel_subtasks=parallel_subtasks,
                        )
                    except Exception as runtime_route_error:
                        print(f"[runtime_host] route apply failed: {runtime_route_error}")
            
                graph_mode = "dynamic" if os.environ.get("GA_DYNAMIC_GRAPH") == "1" else "full"
                agents = self._build_agent_graph(raw_query, executor_progress=executor_progress, graph_mode=graph_mode)
                inputs = list(self.input_items)
                memory_span = _start_manual_span(profiler, "working_memory_prepare", kind="memory", metadata={"history_size": len(self.history)})
                working_memory = _sanitize_runtime_injected_text(
                    _working_memory_message(self.history)
                )
                if working_memory:
                    inputs.append({"role": "user", "content": working_memory})
                _stop_manual_span(memory_span)
                # ── Context Runtime injection (route-gated, env-var-controlled) ──
                context_span = _start_manual_span(profiler, "context_runtime", kind="memory", metadata={"route": route_target})
                context_packet_text = _build_context_runtime(
                    raw_query=raw_query,
                    route=route_target,
                    project_root=PROJECT_ROOT,
                    profiler=profiler,
                )
                context_packet_text = _sanitize_runtime_injected_text(context_packet_text)
                if context_packet_text:
                    inputs.append({"role": "user", "content": context_packet_text})
                _stop_manual_span(context_span)
                # ── Recent conversation context injection (hotfix) ──
                recent_block = ""
                recent_block_chars = 0
                ambiguous_query = False
                recent_span = _start_manual_span(profiler, "recent_turns", kind="memory", metadata={"history_items": len(self.input_items)})
                from core.context.recent_turns import build_recent_conversation_block as _build_recent_block, recent_turns_enabled as _recent_enabled
                if _recent_enabled():
                    recent_block = _build_recent_block(self.input_items, max_turns=5, max_chars=6000)
                    recent_block = _sanitize_runtime_injected_text(recent_block)
                    if recent_block:
                        inputs.append({"role": "user", "content": recent_block})
                        recent_block_chars = len(recent_block)
                from core.context.recent_turns import is_ambiguous_followup as _is_ambiguous
                ambiguous_query = _is_ambiguous(raw_query)
                _stop_manual_span(recent_span)
                # ── Legacy L1/L2 memory injection (P0b) ──
                legacy_memory_block = ""
                legacy_memory_chars = 0
                legacy_memory_sources: list[str] = []
                legacy_memory_span = _start_manual_span(profiler, "legacy_memory", kind="memory", metadata={"gated_by": "GA_OPENAI_LEGACY_MEMORY"})
                if os.environ.get("GA_OPENAI_LEGACY_MEMORY", "1") != "0":
                    from core.memory.legacy_global import read_legacy_l1_l2 as _read_l1l2
                    _legacy_data = _read_l1l2(PROJECT_ROOT)
                    _l1 = _legacy_data.get("l1") or ""
                    _l2 = _legacy_data.get("l2") or ""
                    if _l1 or _l2:
                        _parts: list[str] = []
                        _parts.append("[LEGACY PROJECT MEMORY — This is persistent project memory, not a user request.]")
                        if _l1:
                            _parts.append(f"## L1 (Insights)\n{_l1}")
                            legacy_memory_sources.append("L1")
                        if _l2:
                            _parts.append(f"## L2 (Environment Facts)\n{_l2}")
                            legacy_memory_sources.append("L2")
                        legacy_memory_block = "\n\n".join(_parts)
                        legacy_memory_block = _sanitize_runtime_injected_text(legacy_memory_block)
                        legacy_memory_chars = len(legacy_memory_block)
                        inputs.append({"role": "user", "content": legacy_memory_block})
                _stop_manual_span(legacy_memory_span)
                selected_agent = agents["root"]
                if route_target == "chat":
                    selected_agent = agents["chat"]
                elif execution_mode == "single_agent" and route_target in EXECUTOR_ROUTE_TARGETS:
                    selected_agent = agents["executor"]
                selected_agent_name = getattr(selected_agent, "name", route_target or execution_mode)
                answer_quality_context = {
                    "block": "",
                    "chars": 0,
                    "matched": False,
                    "reason": "disabled",
                }
                if selected_agent_name in ORCHESTRATOR_CONTEXT_AGENTS:
                    if answer_quality_flag:
                        if answer_quality_query_match:
                            answer_quality_context = build_answer_quality_context(
                                raw_query,
                                max_chars=1800,
                            )
                        else:
                            answer_quality_context = {
                                "block": "",
                                "chars": 0,
                                "matched": False,
                                "reason": "query did not match answer-quality planning triggers",
                            }
                    else:
                        answer_quality_context = {
                            "block": "",
                            "chars": 0,
                            "matched": False,
                            "reason": "answer quality guard disabled",
                        }
                problem_framing_context = {
                    "block": "",
                    "chars": 0,
                    "matched": False,
                    "frame": None,
                    "reason": "disabled",
                }
                if selected_agent_name in ORCHESTRATOR_CONTEXT_AGENTS:
                    if problem_framing_flag:
                        if problem_framing_query_match:
                            problem_framing_context = build_problem_framing_context(
                                raw_query,
                                max_chars=1500,
                            )
                        else:
                            problem_framing_context = {
                                "block": "",
                                "chars": 0,
                                "matched": False,
                                "frame": None,
                                "reason": "query did not match problem-framing triggers",
                            }
                    else:
                        problem_framing_context = {
                            "block": "",
                            "chars": 0,
                            "matched": False,
                            "frame": None,
                            "reason": "problem framing disabled",
                        }
                read_prefetch_should_prefetch = False
                read_prefetch_target_file: str | None = None
                read_prefetch_reason = "not_checked"
                read_prefetch_confidence = 0.0
                read_prefetch_max_lines: int | None = None
                read_prefetch_max_chars: int | None = None
                read_prefetch_signals: list[str] = []
                if selected_agent_name in ORCHESTRATOR_CONTEXT_AGENTS:
                    prefetch_decision = detect_read_prefetch(
                        raw_query,
                        project_root=PROJECT_ROOT,
                    )
                    read_prefetch_should_prefetch = bool(prefetch_decision.should_prefetch)
                    read_prefetch_target_file = prefetch_decision.target_file
                    read_prefetch_reason = str(prefetch_decision.reason or "")
                    read_prefetch_confidence = float(prefetch_decision.confidence or 0.0)
                    read_prefetch_max_lines = int(prefetch_decision.max_lines or 0)
                    read_prefetch_max_chars = int(prefetch_decision.max_chars or 0)
                    read_prefetch_signals = list(prefetch_decision.signals or [])
                    if profiler is not None and read_prefetch_should_prefetch:
                        profiler.record_event(
                            "read_prefetch_detected",
                            kind="io",
                            metadata={
                                "should_prefetch": read_prefetch_should_prefetch,
                                "target_file": read_prefetch_target_file,
                                "reason": read_prefetch_reason,
                                "confidence": read_prefetch_confidence,
                                "max_lines": read_prefetch_max_lines,
                                "max_chars": read_prefetch_max_chars,
                                "signals": read_prefetch_signals,
                            },
                        )
                skill_sop_flag = bool(skill_sop_enabled())
                skill_sop_context = {"block": "", "selected_skills": [], "skill_matches": [], "chars": 0, "phase": "planner"}
                if selected_agent_name == "planner_executor" and skill_sop_flag:
                    skill_sop_context = build_optional_sop_context(
                        user_input=raw_query,
                        max_skills=2,
                        max_chars_per_skill=1800,
                        max_total_chars=3500,
                        phase="planner",
                    )
                skill_activation = None
                skill_match_entries = list(skill_sop_context.get("skill_matches") or [])
                skill_match_scores = {
                    str(item.get("name") or ""): float(item.get("score") or 0.0)
                    for item in skill_match_entries
                    if str(item.get("name") or "").strip()
                }
                skill_match_reasons = {
                    str(item.get("name") or ""): list(item.get("reasons") or [])
                    for item in skill_match_entries
                    if str(item.get("name") or "").strip()
                }
                skill_match_applies_to = {
                    str(item.get("name") or ""): list(item.get("applies_to") or [])
                    for item in skill_match_entries
                    if str(item.get("name") or "").strip()
                }
                skill_activation_export_path = ""
                skill_policy_preview: dict[str, Any] = {}
                skill_policy_source_skills: list[str] = []
                skill_policy_disabled_tools: list[str] = []
                skill_policy_suppressed_context_sections: list[str] = []
                skill_policy_max_turns: int | None = None
                skill_policy_max_prompt_chars: int | None = None
                skill_policy_warnings: list[str] = []
                skill_memory_write_allowed = False
                if skill_sop_context.get("selected_skills"):
                    try:
                        skill_activation = build_skill_activation(
                            user_input=raw_query,
                            phase=str(skill_sop_context.get("phase") or "planner"),
                            skill_sop_context=skill_sop_context,
                            run_id=self._profile_run_id,
                        )
                        try:
                            skill_activation_export_path = str(export_skill_activation(skill_activation))
                        except Exception as exc:
                            print(f"[skill_activation] export failed: {exc}")
                        skill_policy_source_skills = list(
                            skill_activation.execution_policy.get("source_skills") or []
                        )
                        skill_policy_disabled_tools = list(
                            skill_activation.execution_policy.get("disabled_tools") or []
                        )
                        skill_policy_suppressed_context_sections = list(
                            skill_activation.execution_policy.get("suppressed_context_sections") or []
                        )
                        skill_policy_max_turns = skill_activation.execution_policy.get("max_turns")
                        skill_policy_max_prompt_chars = skill_activation.execution_policy.get("max_prompt_chars")
                        skill_policy_warnings = list(skill_activation.policy_warnings or [])
                        skill_memory_write_allowed = bool(skill_activation.memory_write_allowed)
                        # ── P2-4: store policy for runtime enforcement ──
                        self._active_policy = skill_activation.execution_policy
                        skill_policy_preview = {
                            "source_skills": skill_policy_source_skills,
                            "disabled_tools": skill_policy_disabled_tools,
                            "suppressed_context_sections": skill_policy_suppressed_context_sections,
                            "tool_schema_policy": skill_activation.execution_policy.get("tool_schema_policy"),
                            "context_policy": skill_activation.execution_policy.get("context_policy"),
                            "max_turns": skill_policy_max_turns,
                            "max_prompt_chars": skill_policy_max_prompt_chars,
                        }
                        if profiler is not None:
                            profiler.record_event(
                                "skill_activation",
                                kind="agent",
                                metadata={
                                    "activation_id": skill_activation.activation_id,
                                    "phase": skill_activation.phase,
                                    "selected_skills": list(skill_activation.selected_skills),
                                    "prompt_chars_added": skill_activation.prompt_chars_added,
                                    "policy_preview": skill_policy_preview,
                                    "policy_warnings": skill_policy_warnings,
                                    "memory_write_allowed": skill_memory_write_allowed,
                                    "export_path": skill_activation_export_path,
                                },
                            )
                    except Exception as exc:
                        print(f"[skill_activation] build failed: {exc}")
                self._update_model_audit_context(
                    source=source,
                    attempt=attempt + 1,
                    route_target=route_target,
                    execution_mode=execution_mode,
                    agent_name=selected_agent_name,
                    turn=max(seen_turn, 1),
                    skill_sop_enabled=skill_sop_flag,
                    skill_phase=str(skill_sop_context.get("phase") or "planner"),
                    selected_skills=list(skill_sop_context.get("selected_skills") or []),
                    skill_match_scores=skill_match_scores,
                    skill_match_reasons=skill_match_reasons,
                    selected_skill_applies_to=skill_match_applies_to,
                    skill_sop_chars=int(skill_sop_context.get("chars") or 0),
                    answer_quality_enabled=answer_quality_flag,
                    answer_quality_route_override=answer_quality_route_override,
                    answer_quality_context_injected=bool(answer_quality_context.get("block")),
                    answer_quality_context_chars=int(answer_quality_context.get("chars") or 0),
                    answer_quality_reason=str(answer_quality_context.get("reason") or ""),
                    problem_framing_enabled=problem_framing_flag,
                    problem_framing_context_injected=bool(problem_framing_context.get("block")),
                    problem_framing_context_chars=int(problem_framing_context.get("chars") or 0),
                    problem_framing_frame=str(problem_framing_context.get("frame") or ""),
                    problem_framing_reason=str(problem_framing_context.get("reason") or ""),
                    read_prefetch_should_prefetch=read_prefetch_should_prefetch,
                    read_prefetch_target_file=read_prefetch_target_file,
                    read_prefetch_reason=read_prefetch_reason,
                    read_prefetch_confidence=read_prefetch_confidence,
                    read_prefetch_max_lines=read_prefetch_max_lines,
                    read_prefetch_max_chars=read_prefetch_max_chars,
                    skill_activation_id=getattr(skill_activation, "activation_id", None),
                    skill_policy_preview=skill_policy_preview or None,
                    skill_policy_source_skills=skill_policy_source_skills or None,
                    skill_policy_disabled_tools=skill_policy_disabled_tools or None,
                    skill_policy_suppressed_context_sections=skill_policy_suppressed_context_sections or None,
                    skill_policy_max_turns=skill_policy_max_turns,
                    skill_policy_max_prompt_chars=skill_policy_max_prompt_chars,
                    skill_policy_warnings=skill_policy_warnings or None,
                    skill_memory_write_allowed=skill_memory_write_allowed,
                    recent_turns_injected=bool(recent_block),
                    recent_turns_chars=recent_block_chars,
                    ambiguous_followup=ambiguous_query,
                    legacy_memory_injected=bool(legacy_memory_block),
                    legacy_memory_chars=legacy_memory_chars,
                    legacy_memory_sources=legacy_memory_sources,
                )
                # 如果规则匹配命中，添加路由提示
                if route_hint and selected_agent is agents["root"]:
                    inputs.append({"role": "user", "content": _sanitize_runtime_injected_text(route_hint)})
                answer_quality_block = _sanitize_runtime_injected_text(
                    str(answer_quality_context.get("block") or "").strip()
                )
                if selected_agent_name in ORCHESTRATOR_CONTEXT_AGENTS and answer_quality_block:
                    inputs.append({"role": "user", "content": answer_quality_block})
                problem_framing_block = _sanitize_runtime_injected_text(
                    str(problem_framing_context.get("block") or "").strip()
                )
                if selected_agent_name in ORCHESTRATOR_CONTEXT_AGENTS and problem_framing_block:
                    inputs.append({"role": "user", "content": problem_framing_block})
                optional_sop_block = _sanitize_runtime_injected_text(
                    str(skill_sop_context.get("block") or "").strip()
                )
                if selected_agent_name == "planner_executor" and optional_sop_block:
                    inputs.append({"role": "user", "content": optional_sop_block})
                # ── Read prefetch context injection (P2-1) ──
                prefetch_injected = False
                prefetch_chars = 0
                prefetch_skip_reason = "disabled"
                if is_read_prefetch_enabled() and read_prefetch_should_prefetch and read_prefetch_target_file:
                    content, status, prefetch_meta = safe_read_prefetch_content(
                        read_prefetch_target_file,
                        PROJECT_ROOT,
                        max_lines=read_prefetch_max_lines or 200,
                        max_chars=read_prefetch_max_chars or 12000,
                    )
                    if content is not None and status == "ok":
                        prefetch_block = build_read_prefetch_context(
                            content,
                            read_prefetch_target_file,
                            read_prefetch_reason,
                            read_prefetch_confidence,
                            bool(prefetch_meta.get("truncated")),
                        )
                        prefetch_block = _sanitize_runtime_injected_text(prefetch_block)
                        inputs.append({"role": "user", "content": prefetch_block})
                        prefetch_injected = True
                        prefetch_chars = len(prefetch_block)
                    else:
                        prefetch_skip_reason = f"{status}: {prefetch_meta.get('reason', 'unknown')}"
                    if profiler is not None:
                        profiler.record_event(
                            "read_prefetch_injection",
                            kind="io",
                            metadata={
                                "injected": prefetch_injected,
                                "target_file": read_prefetch_target_file,
                                "chars": prefetch_chars,
                                "lines": prefetch_meta.get("injected_lines"),
                                "reason": read_prefetch_reason,
                                "confidence": read_prefetch_confidence,
                                "truncated": prefetch_meta.get("truncated"),
                                "skip_reason": prefetch_skip_reason if not prefetch_injected else None,
                            },
                        )
                if profiler is not None:
                    profiler.record_event(
                        "recent_turns_injection",
                        kind="memory",
                        metadata={
                            "injected": bool(recent_block),
                            "chars": recent_block_chars,
                            "history_items": len(self.input_items),
                            "ambiguous_followup": ambiguous_query,
                            "clarification_injected": bool(ambiguous_query and not recent_block),
                        },
                    )
                if profiler is not None:
                    profiler.record_event(
                        "legacy_memory_injection",
                        kind="memory",
                        metadata={
                            "injected": bool(legacy_memory_block),
                            "chars": legacy_memory_chars,
                            "sources": legacy_memory_sources,
                        },
                    )
                # ── Ambiguous follow-up guard ──
                if ambiguous_query and not recent_block:
                    from core.context.recent_turns import build_clarification_request as _clarify
                    inputs.append({"role": "user", "content": _clarify()})
                inputs.append({"role": "user", "content": raw_query})

                # ── M5: Canonical context assembly gate ──
                # When GA_CONTEXT_RUNTIME_MODE=inject, rebuild inputs through
                # the OpenAIContextAdapter to add structural markers and enforce
                # canonical ordering. Legacy path (default/preview) is unchanged.
                _context_mode = os.environ.get("GA_CONTEXT_RUNTIME_MODE", "preview")
                if _context_mode == "inject":
                    from core.context.adapters import OpenAIContextAdapter
                    _adapter = OpenAIContextAdapter(policy_mode="inject")
                    _clarify_text = ""
                    if ambiguous_query and not recent_block:
                        from core.context.recent_turns import build_clarification_request as _clarify
                        _clarify_text = _clarify()
                    inputs = _adapter.build_inputs(
                        input_items=list(self.input_items),
                        working_memory=working_memory,
                        context_packet=context_packet_text,
                        recent_block=recent_block,
                        legacy_memory=legacy_memory_block,
                        route_hint=route_hint if (route_hint and selected_agent is agents["root"]) else "",
                        answer_quality=answer_quality_block,
                        sop_context=optional_sop_block,
                        prefetch_block=prefetch_block if prefetch_injected else "",
                        clarification=_clarify_text,
                        raw_query=raw_query,
                    )
                    if profiler is not None:
                        profiler.record_event(
                            "canonical_context_assembly",
                            kind="memory",
                            metadata={
                                "mode": "inject",
                                "block_count": len(inputs),
                                "total_chars": sum(
                                    len(str(i.get("content", ""))) for i in inputs
                                ),
                            },
                        )

                if profiler is not None:
                    profiler.record_event(
                        "route_selected",
                        kind="agent",
                        metadata={
                            "target": route_target,
                            "execution_mode": execution_mode,
                            "selected_agent": selected_agent_name,
                            "parallel_subtask_count": len(parallel_subtasks),
                            "skill_sop_enabled": skill_sop_flag,
                            "skill_phase": str(skill_sop_context.get("phase") or "planner"),
                            "selected_skills": list(skill_sop_context.get("selected_skills") or []),
                            "skill_match_scores": skill_match_scores,
                            "skill_match_reasons": skill_match_reasons,
                            "selected_skill_applies_to": skill_match_applies_to,
                            "skill_sop_chars": int(skill_sop_context.get("chars") or 0),
                            "answer_quality_enabled": answer_quality_flag,
                            "answer_quality_route_override": answer_quality_route_override,
                            "answer_quality_context_injected": bool(answer_quality_context.get("block")),
                            "answer_quality_context_chars": int(answer_quality_context.get("chars") or 0),
                            "answer_quality_reason": str(answer_quality_context.get("reason") or ""),
                            "read_prefetch_should_prefetch": read_prefetch_should_prefetch,
                            "read_prefetch_target_file": read_prefetch_target_file,
                            "read_prefetch_reason": read_prefetch_reason,
                            "read_prefetch_confidence": read_prefetch_confidence,
                            "read_prefetch_max_lines": read_prefetch_max_lines,
                            "read_prefetch_max_chars": read_prefetch_max_chars,
                            "skill_activation_id": getattr(skill_activation, "activation_id", None),
                            "skill_policy_preview": skill_policy_preview or None,
                            "skill_policy_source_skills": skill_policy_source_skills,
                            "skill_policy_disabled_tools": skill_policy_disabled_tools,
                            "skill_policy_suppressed_context_sections": skill_policy_suppressed_context_sections,
                            "skill_policy_max_turns": skill_policy_max_turns,
                            "skill_policy_max_prompt_chars": skill_policy_max_prompt_chars,
                            "skill_policy_warnings": skill_policy_warnings,
                            "skill_memory_write_allowed": skill_memory_write_allowed,
                        },
                    )
                _stop_manual_span(planning_span)
                execution_span = _start_manual_span(
                    profiler,
                    "selected_agent_execution",
                    kind="agent",
                    metadata={"attempt": attempt + 1, "selected_agent": selected_agent_name, "route_target": route_target},
                )
                llm_span = _start_manual_span(
                    profiler,
                    "orchestrator_streamed_run",
                    kind="llm",
                    metadata={"attempt": attempt + 1, "selected_agent": selected_agent_name},
                )
                stream_span = _start_manual_span(
                    profiler,
                    "stream_events",
                    kind="frontend",
                    metadata={"attempt": attempt + 1, "selected_agent": selected_agent_name},
                )
                self._store_executor_result_state(None)
                result = Runner.run_streamed(selected_agent, input=inputs, max_turns=100)
                self._active_stream_result = result

                async for event in result.stream_events():
                    if self.stop_sig:
                        result.cancel(mode="immediate")
                        raise asyncio.CancelledError()

                    while result.current_turn > seen_turn:
                        if runtime_host is not None and seen_turn > 0:
                            try:
                                runtime_host.complete_llm_turn(
                                    seen_turn,
                                    selected_agent=selected_agent_name,
                                    result_summary=full_text[-300:],
                                )
                            except Exception:
                                pass
                        _stop_manual_span(active_llm_turn_span)
                        seen_turn += 1
                        self._update_model_audit_context(
                            source=source,
                            attempt=attempt + 1,
                            route_target=route_target,
                            execution_mode=execution_mode,
                            agent_name=selected_agent_name,
                            turn=seen_turn,
                        )
                        active_llm_turn_span = _start_manual_span(
                            profiler,
                            f"llm_call_turn_{seen_turn}",
                            kind="llm",
                            metadata={"turn": seen_turn, "attempt": attempt + 1, "selected_agent": selected_agent_name},
                        )
                        if runtime_host is not None:
                            try:
                                runtime_host.begin_llm_turn(seen_turn, selected_agent=selected_agent_name)
                            except Exception:
                                pass
                        if full_text and not full_text.endswith("\n\n"):
                            full_text += "\n\n"
                        full_text += f"**LLM Running (Turn {seen_turn}) ...**\n\n"
                        flush_progress(force=True)

                    if isinstance(event, RawResponsesStreamEvent):
                        raw_event = event.data
                        if getattr(raw_event, "type", "") == "response.output_text.delta":
                            delta = str(getattr(raw_event, "delta", "") or "")
                            if delta:
                                delta = _strip_stream_artifacts(delta)
                                if delta:
                                    full_text += delta
                                    flush_progress(force="\n" in delta)
                        continue

                    if getattr(event, "type", "") == "run_item_stream_event":
                        event_name = getattr(event, "name", "")
                        if event_name == "tool_called":
                            _stop_manual_span(active_tool_span)
                            tool_name = self._tool_name_from_item(event.item)
                            active_tool_name = tool_name
                            active_tool_span = _start_manual_span(
                                profiler,
                                f"tool_call:{tool_name}",
                                kind="tool",
                                metadata={"tool": tool_name, "attempt": attempt + 1, "turn": max(seen_turn, 1)},
                            )
                            if runtime_host is not None:
                                try:
                                    runtime_host.request_tool(tool_name, risk_level="medium")
                                except Exception:
                                    pass
                        elif event_name == "tool_output":
                            _stop_manual_span(active_tool_span)
                            active_tool_span = None
                            tool_output_summary = self._compact_event_text(getattr(event.item, "output", None), max_len=200)
                            if active_tool_name == "run_genericagent_executor":
                                executor_state = self._consume_executor_result_state()
                                if self._should_skip_planner_followup(executor_state):
                                    planner_followup_override = executor_state
                                    if profiler is not None:
                                        profiler.record_event(
                                            "orchestrator_skip_planner_followup",
                                            kind="agent",
                                            metadata={
                                                "reason": executor_state.get("shortcut_reason") or "read_shortcut_final_answer_ready",
                                                "shortcut_type": executor_state.get("shortcut_type"),
                                                "confidence": executor_state.get("shortcut_confidence"),
                                                "saved_llm_call_estimate": 1,
                                            },
                                        )
                                    try:
                                        result.cancel(mode="immediate")
                                    except Exception:
                                        pass
                                    runtime_complete_active_tool(summary=tool_output_summary)
                                    break
                            runtime_complete_active_tool(summary=tool_output_summary)
                        elif event_name in {"handoff_requested", "handoff_occured"}:
                            target = getattr(event.item, "target_agent", None)
                            target_name = getattr(target, "name", "") if target is not None else ""
                            if profiler is not None:
                                profiler.record_event(
                                    event_name,
                                    kind="agent",
                                    metadata={"target_agent": target_name},
                                )
                            if runtime_host is not None and target_name:
                                try:
                                    runtime_host.record_handoff(
                                        target_agent=target_name,
                                        completed=(event_name == "handoff_occured"),
                                    )
                                except Exception:
                                    pass
                            if target_name:
                                selected_agent_name = target_name
                                self._update_model_audit_context(
                                    source=source,
                                    attempt=attempt + 1,
                                    route_target=route_target,
                                    execution_mode=execution_mode,
                                    agent_name=selected_agent_name,
                                    turn=max(seen_turn, 1),
                                )

                    progress_text = self._progress_text_for_event(event)
                    if progress_text:
                        if full_text and not full_text.endswith("\n"):
                            full_text += "\n"
                        full_text += f"{progress_text}\n\n"
                        flush_progress(force=True)

                _stop_manual_span(active_tool_span)
                active_tool_span = None
                _stop_manual_span(active_llm_turn_span)
                active_llm_turn_span = None
                _stop_manual_span(stream_span)
                stream_span = None
                _stop_manual_span(llm_span)
                llm_span = None
                _stop_manual_span(execution_span)
                execution_span = None

                if planner_followup_override is not None:
                    final_text = str(planner_followup_override.get("final_answer_text") or "").strip()
                    if not full_text.strip():
                        full_text = _inject_turn_markers(final_text or "[Empty response]")
                        seen_turn = max(1, full_text.count("LLM Running (Turn"))
                    elif final_text and final_text not in full_text:
                        if not full_text.endswith("\n\n"):
                            full_text += "\n\n"
                        full_text += final_text

                    try:
                        self.input_items = result.to_input_list(mode="normalized")
                        # Filter out internal execution-engine prompts
                        self.input_items = [
                            item for item in self.input_items
                            if not _is_internal_user_message(item)
                        ]
                    except Exception:
                        pass
                    if self.llmclient:
                        self.llmclient.backend.history = list(self.input_items)
                    user_line = smart_format(raw_query.replace("\n", " "), max_str_len=200)
                    agent_line = _sanitize_runtime_injected_text(
                        _extract_summary_line(final_text)
                        or smart_format(final_text.replace("\n", " "), max_str_len=300)
                    )
                    self.history.append(f"[USER]: {user_line}")
                    self.history.append(f"[Agent] {agent_line}")
                    io_span = _start_manual_span(
                        profiler,
                        "save_model_response_log",
                        kind="io",
                        metadata={"attempt": attempt + 1, "shortcut_type": planner_followup_override.get("shortcut_type")},
                    )
                    _log_exchange(raw_query, full_text, self.input_items)
                    _stop_manual_span(io_span)

                    for hook in self._turn_end_hooks.values():
                        try:
                            hook(
                                {
                                    "turn": max(seen_turn, full_text.count("LLM Running (Turn")),
                                    "summary": agent_line,
                                    "exit_reason": {
                                        "result": "DONE",
                                        "shortcut_type": planner_followup_override.get("shortcut_type"),
                                    },
                                }
                            )
                        except Exception:
                            pass
                    runtime_complete_active_turn()
                    runtime_finalize_success(agent_line)
                    display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 1)})
                    return

                if result.run_loop_exception:
                    raise result.run_loop_exception

                final_output = result.final_output
                final_text = (
                    final_output if isinstance(final_output, str) else str(final_output or "")
                ).strip()
                if _should_fallback_to_classic(route_target, final_text=final_text):
                    fallback_span = _start_manual_span(profiler, "classic_executor_fallback", kind="tool", metadata={"reason": "unusable_output"})
                    final_text = await asyncio.to_thread(
                        self._run_classic_executor_task,
                        raw_query,
                        _classic_executor_plan(f"Unusable orchestration output: {final_text or '[empty]'}"),
                    )
                    _stop_manual_span(fallback_span)
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
                # Filter out internal execution-engine prompts
                self.input_items = [
                    item for item in self.input_items
                    if not _is_internal_user_message(item)
                ]
                if self.llmclient:
                    self.llmclient.backend.history = list(self.input_items)
                user_line = smart_format(raw_query.replace("\n", " "), max_str_len=200)
                agent_line = _sanitize_runtime_injected_text(
                    _extract_summary_line(final_text)
                    or smart_format(final_text.replace("\n", " "), max_str_len=300)
                )
                self.history.append(f"[USER]: {user_line}")
                self.history.append(f"[Agent] {agent_line}")
                io_span = _start_manual_span(profiler, "save_model_response_log", kind="io", metadata={"attempt": attempt + 1})
                _log_exchange(raw_query, full_text, self.input_items)
                _stop_manual_span(io_span)

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
                runtime_complete_active_turn()
                runtime_finalize_success(agent_line)
                display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})
                return  # 成功完成，退出重试循环

            except (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError) as e:
                # 超时/连接错误 - 自动重试
                error_name = type(e).__name__
                if attempt < MAX_RETRIES - 1:
                    if profiler is not None:
                        profiler.record_event("retry_scheduled", kind="io", metadata={"attempt": attempt + 2, "error": error_name})
                    retry_msg = f"[WARN] {error_name}: {e}. Retrying in {RETRY_DELAY}s... (attempt {attempt + 2}/{MAX_RETRIES})"
                    print(retry_msg)
                    display_queue.put({"next": f"\n**{retry_msg}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                    await asyncio.sleep(RETRY_DELAY)
                    RETRY_DELAY *= 1.5  # 指数退避
                    continue
                else:
                    # 重试次数用尽
                    self._profile_status = "error"
                    error_msg = f"[ERROR] {error_name}: {e}. All {MAX_RETRIES} retries failed."
                    runtime_complete_active_tool(error=error_msg)
                    if runtime_host is not None:
                        try:
                            runtime_host.fail_session(error=error_msg)
                        except Exception:
                            pass
                    print(error_msg)
                    display_queue.put({"done": f"\n**{error_msg}**\n\n请尝试重新发送请求。", "source": "system", "turn": max(seen_turn, 0)})
                    return
            except asyncio.CancelledError:
                if self._user_abort_requested or self.stop_sig:
                    self._profile_status = "aborted"
                    runtime_complete_active_tool(error="user_abort")
                    if runtime_host is not None:
                        try:
                            runtime_host.request_stop(reason="user_abort")
                        except Exception:
                            pass
                    display_queue.put({"done": full_text + "\n\n[已取消]", "source": "system", "turn": max(seen_turn, 0)})
                    return
                warn_msg = "[WARN] Unexpected internal cancellation."
                if attempt < MAX_RETRIES - 1:
                    print(warn_msg)
                    display_queue.put({"next": f"\n**{warn_msg} Retrying...**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                    await asyncio.sleep(RETRY_DELAY)
                    RETRY_DELAY *= 1.5
                    continue
                self._profile_status = "error"
                runtime_complete_active_tool(error=warn_msg)
                if runtime_host is not None:
                    try:
                        runtime_host.fail_session(error=warn_msg)
                    except Exception:
                        pass
                display_queue.put({"done": full_text or f"\n**{warn_msg}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                return
            except Exception as e:
                runtime_complete_active_tool(error=format_error(e))
                if _should_fallback_to_classic(route_target, exc=e):
                    fallback_span = _start_manual_span(profiler, "classic_executor_fallback", kind="tool", metadata={"reason": type(e).__name__})
                    fallback_text = await asyncio.to_thread(
                        self._run_classic_executor_task,
                        raw_query,
                        _classic_executor_plan(f"{type(e).__name__}: {e}"),
                    )
                    _stop_manual_span(fallback_span)
                    fallback_text = (fallback_text or "").strip()
                    if fallback_text:
                        full_text = _inject_turn_markers(fallback_text)
                        user_line = smart_format(raw_query.replace("\n", " "), max_str_len=200)
                        agent_line = _sanitize_runtime_injected_text(
                            _extract_summary_line(fallback_text)
                            or smart_format(
                                fallback_text.replace("\n", " "),
                                max_str_len=300,
                            )
                        )
                        self.history.append(f"[USER]: {user_line}")
                        self.history.append(f"[Agent] {agent_line}")
                        io_span = _start_manual_span(profiler, "save_model_response_log", kind="io", metadata={"attempt": attempt + 1, "fallback": True})
                        _log_exchange(raw_query, full_text, self.input_items)
                        _stop_manual_span(io_span)
                        runtime_complete_active_turn()
                        runtime_finalize_success(agent_line)
                        display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})
                        return
                # 其他异常 - 直接报错
                self._profile_status = "error"
                if runtime_host is not None:
                    try:
                        runtime_host.fail_session(error=format_error(e))
                    except Exception:
                        pass
                import traceback
                traceback.print_exc()
                display_queue.put({"done": f"\n**[ERROR] {type(e).__name__}: {e}**\n\n", "source": "system", "turn": max(seen_turn, 0)})
                return
            finally:
                _stop_manual_span(active_tool_span)
                _stop_manual_span(active_llm_turn_span)
                _stop_manual_span(stream_span if 'stream_span' in locals() else None)
                _stop_manual_span(llm_span if 'llm_span' in locals() else None)
                _stop_manual_span(execution_span if 'execution_span' in locals() else None)
                _stop_manual_span(planning_span if 'planning_span' in locals() else None)
                self._active_stream_result = None
                self._run_store = None

        # 不应该到达这里
        display_queue.put({"done": full_text, "source": source, "turn": max(seen_turn, 0)})

    def _drain_task(
        self,
        raw_query: str,
        source: str,
        display_queue: queue.Queue[dict[str, Any]],
    ) -> None:
        # Reuse a shared event loop instead of creating/destroying one per task.
        if self._active_loop is None or self._active_loop.is_closed():
            self._active_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._active_loop)
        loop = self._active_loop
        task = loop.create_task(self._run_task_async(raw_query, source, display_queue))
        self._active_task = task
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            display_queue.put({"done": "[Interrupted]", "source": source})
        finally:
            self._active_stream_result = None
            self._active_task = None
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                for pending_task in pending:
                    pending_task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            # ── Auto-maintenance hook (GA_AUTO_MAINTENANCE=1) ──
            try:
                if os.environ.get("GA_AUTO_MAINTENANCE", "0") == "1":
                    self._maintenance_turn_count = getattr(self, "_maintenance_turn_count", 0) + 1
                    if self._maintenance_turn_count % 10 == 0:
                        from core.memory.maintenance import run_memory_maintenance
                        import threading as _maint_threading
                        _t = _maint_threading.Thread(
                            target=run_memory_maintenance,
                            args=(PROJECT_ROOT,),
                            daemon=True,
                            name="auto-maintenance",
                        )
                        _t.start()
            except Exception:
                pass

    def run(self) -> None:
        while True:
            task = self.task_queue.get()
            raw_query = task["query"]
            source = task["source"]
            display_queue = task["output"]
            run_id = task.get("run_id") or uuid.uuid4().hex
            raw_query = self._handle_slash_cmd(raw_query, display_queue)
            if raw_query is None:
                self.task_queue.task_done()
                continue

            self._running = True
            self.stop_sig = False
            self._user_abort_requested = False
            self._profile_status = "success"
            self._profile_run_id = run_id
            self.active_profiler = RuntimeProfiler() if profiling_enabled() else None
            self._runtime_host = None
            self._runtime_session_id = None
            if self.active_profiler is not None:
                self.active_profiler.start_run(
                    run_id=run_id,
                    name="openai_orchestrated_request",
                    metadata={"backend": "openai-agents", "source": source},
                )
            try:
                from core.runtime.host import RuntimeHost

                self._runtime_host = RuntimeHost(
                    project_root=PROJECT_ROOT,
                    agent_name="openai_orchestrated_agent",
                )
                runtime_state = self._runtime_host.start_session(
                    user_intent=raw_query,
                    source=source,
                    session_id=run_id,
                )
                self._runtime_session_id = runtime_state.session_id
            except Exception as runtime_host_error:
                print(f"[runtime_host] init failed: {runtime_host_error}")
            try:
                self._drain_task(raw_query, source, display_queue)
            except Exception as e:
                self._profile_status = "error"
                if self._runtime_host is not None:
                    try:
                        self._runtime_host.fail_session(error=format_error(e))
                    except Exception:
                        pass
                display_queue.put(
                    {
                        "done": f"[OpenAI Agents Error]\n\n```\n{format_error(e)}\n```",
                        "source": source,
                    }
                )
            finally:
                if self.active_profiler is not None:
                    try:
                        summary = self.active_profiler.end_run(status=_profile_status_label(self._profile_status))
                        profile_path = build_profile_path(os.path.join(PROJECT_ROOT, "temp", "profiles"), self._profile_run_id or run_id)
                        self.active_profiler.export_json(profile_path)
                        print(format_profile_summary(summary, top_n=10))
                        print(f"[PROFILE] saved={profile_path}")
                    except Exception as profile_error:
                        print(f"[PROFILE] export failed: {profile_error}")
                    finally:
                        self.active_profiler = None
                        self._profile_run_id = None
                self._store_executor_result_state(None)
                self._running = False
                self.stop_sig = False
                self._user_abort_requested = False
                self._runtime_host = None
                self._runtime_session_id = None
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


# ══ DEPRECATED: use `ga run-openai/serve-openai` CLI instead (core/cli.py). ══
# This block is kept for the root openai_agentmain.py wrapper.
# Do NOT add new features here.
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
