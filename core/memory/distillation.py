"""
Distillation — memory distillation trigger and candidate builder.

Extracted from ga.py:do_start_long_term_update() so the OpenAI path can
trigger distillation without importing ga.py internals.

Gated by GA_OPENAI_DISTILLATION:
  "0"       — off, do nothing
  "preview" — generate candidate, log to disk, do NOT write to inbox (default)
  "write"   — generate candidate AND append to history_memory_inbox.md

Classic path behavior is unchanged — ga.py continues to use its own
do_start_long_term_update() pathway.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ══════════════════════════════════════════════════════════════════════
# Env-var gate
# ══════════════════════════════════════════════════════════════════════

_DISTILLATION_MODE_VAR = "GA_OPENAI_DISTILLATION"
_DEFAULT_MODE = "preview"
_VALID_MODES = {"0", "off", "preview", "write"}


def get_distillation_mode() -> str:
    """Return 'off', 'preview', or 'write'. Default is 'preview'."""
    raw = os.environ.get(_DISTILLATION_MODE_VAR, _DEFAULT_MODE).strip().lower()
    if raw in ("0", "off"):
        return "off"
    if raw == "write":
        return "write"
    return "preview"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


# ══════════════════════════════════════════════════════════════════════
# Distillation trigger prompt
# ══════════════════════════════════════════════════════════════════════

def trigger_distillation(project_root: str | Path | None = None) -> str:
    """Generate the distillation instruction prompt.

    This is the prompt that instructs the agent to review recent work,
    extract verified facts, and prepare memory updates.

    Returns empty string when distillation mode is 'off'.
    """
    mode = get_distillation_mode()
    if mode == "off":
        return ""

    root = Path(project_root) if project_root else _default_root()

    prompt = (
        "### [总结提炼经验] 既然你觉得当前任务有重要信息需要记忆，"
        "请提取最近一次任务中【事实验证成功且长期有效】的环境事实、用户偏好、重要步骤，更新记忆。\n"
        "本工具是标记开启结算过程，若已在更新记忆过程或没有值得记忆的点，忽略本次调用。\n"
        "**提取行动验证成功的信息**：\n"
        "- **环境事实**（路径/凭证/配置）→ `file_patch` 更新 L2，同步 L1\n"
        "- **复杂任务经验**（关键坑点/前置条件/重要步骤）→ L3 精简 SOP"
        "（只记你被坑得多次重试的核心要点）\n"
        "**禁止**：临时变量、具体推理过程、未验证信息、通用常识、你可以轻松复现的细节。\n"
        "**操作**：严格遵循提供的L0的记忆更新SOP。先 `file_read` 看现有 → 判断类型 → "
        "最小化更新 → 无新内容跳过，保证对记忆库最小局部修改。\n"
    )

    # Append current L1/L2 memory (same as Classic)
    from .legacy_global import build_legacy_memory_block

    mem_block = build_legacy_memory_block(root)
    if mem_block:
        prompt += mem_block

    return prompt


# ══════════════════════════════════════════════════════════════════════
# Distillation candidate builder
# ══════════════════════════════════════════════════════════════════════

def build_distillation_candidate(
    *,
    summary: str,
    source: str = "openai",
    run_id: str = "",
    task: str = "",
    session: str = "",
    files_touched: list[str] | None = None,
    questions: list[str] | None = None,
    is_proposed: bool = False,
) -> dict[str, Any]:
    """Build a structured distillation candidate.

    This is a PREVIEW candidate — it does NOT write to inbox unless
    the mode is 'write' and write_distillation_candidate() is called.

    Args:
        summary: The distilled summary (agent's extracted memory).
        source: Source path — "openai" or "classic".
        run_id: Profile run ID for traceability.
        task: Task description.
        session: Session identifier.
        files_touched: Files modified during the task.
        questions: Questions the distillation addresses.
        is_proposed: True if this is a proposal (not yet executed).
                     Proposed candidates must NOT be written to inbox.

    Returns:
        Dict with candidate data and metadata.
    """
    now = _utc_now_iso()
    title = (summary.split("\n")[0] if summary else "Untitled")[:80].strip()

    candidate: dict[str, Any] = {
        "title": title,
        "summary": summary,
        "source": source,
        "run_id": run_id,
        "task": task,
        "session": session,
        "is_proposed": is_proposed,
        "files_touched": list(files_touched or []),
        "questions": list(questions or []),
        "generated_at": now,
        "mode": get_distillation_mode(),
    }

    return candidate


def format_inbox_entry(candidate: dict[str, Any]) -> str:
    """Format a distillation candidate as a history_memory_inbox.md entry.

    Matches the Classic path inbox format:
        ## <title>
        Saved At: <date>
        Source: <source>
        Run: <run_id>
        Session: <session>
        Task: <task>
        <summary>

    Returns empty string if candidate is marked as proposed (not executed).
    """
    if candidate.get("is_proposed"):
        return ""  # Never write proposed changes to inbox

    title = candidate.get("title", "Untitled")
    saved_at = candidate.get("generated_at", _utc_now_iso())[:10]
    source = candidate.get("source", "unknown")
    run_id = candidate.get("run_id", "")
    session = candidate.get("session", "")
    task = candidate.get("task", "")
    summary = candidate.get("summary", "")

    lines = [
        f"## {title}",
        f"Saved At: {saved_at}",
        f"Source: {source}",
    ]
    if run_id:
        lines.append(f"Run: {run_id}")
    if session:
        lines.append(f"Session: {session}")
    if task:
        lines.append(f"Task: {task}")

    files = candidate.get("files_touched") or []
    if files:
        lines.append(f"Files Touched: {', '.join(files[:10])}")

    questions = candidate.get("questions") or []
    for q in questions:
        lines.append(f"- {q}")

    lines.append("")
    lines.append(summary)
    lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# Write gate
# ══════════════════════════════════════════════════════════════════════

def write_distillation_candidate(
    candidate: dict[str, Any],
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """Write a distillation candidate to history_memory_inbox.md.

    ONLY writes when GA_OPENAI_DISTILLATION='write'.
    In 'preview' mode, logs the candidate to temp/distillation_previews/ instead.
    In 'off' mode, does nothing.

    Refuses to write if candidate['is_proposed'] is True.

    Returns a result dict with {written, path, reason, mode}.
    """
    mode = get_distillation_mode()
    root = Path(project_root) if project_root else _default_root()

    result: dict[str, Any] = {
        "written": False,
        "path": "",
        "reason": "",
        "mode": mode,
    }

    if mode == "off":
        result["reason"] = "distillation disabled"
        return result

    if candidate.get("is_proposed"):
        result["reason"] = "refused: candidate is a proposal, not executed fact"
        return result

    entry = format_inbox_entry(candidate)
    if not entry:
        result["reason"] = "empty candidate (or proposed-only)"
        return result

    if mode == "preview":
        # Preview: write candidate JSON to temp/ for inspection
        preview_dir = root / "temp" / "distillation_previews"
        preview_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        run_id = candidate.get("run_id", "") or f"draft_{ts}"
        preview_path = preview_dir / f"{run_id}_{ts}.json"
        try:
            preview_data = {
                "candidate": candidate,
                "formatted_entry": entry,
                "mode": mode,
                "generated_at": candidate.get("generated_at", _utc_now_iso()),
            }
            preview_path.write_text(
                json.dumps(preview_data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            result["path"] = str(preview_path)
            result["reason"] = "preview: logged to temp/distillation_previews/"
        except Exception as e:
            result["reason"] = f"preview write failed: {e}"
        return result

    # mode == "write"
    inbox_path = root / "memory" / "history_memory_inbox.md"
    try:
        # Ensure memory dir exists
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        # Append
        existing = ""
        if inbox_path.is_file():
            existing = inbox_path.read_text(encoding="utf-8", errors="replace")
        content = (existing + "\n" + entry).strip() + "\n"
        inbox_path.write_text(content, encoding="utf-8")
        result["written"] = True
        result["path"] = str(inbox_path)
        result["reason"] = "appended to history_memory_inbox.md"
    except Exception as e:
        result["reason"] = f"write failed: {e}"

    return result
