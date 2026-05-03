"""Dry-run detector for analysis-oriented single-file prefetch suggestions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


_ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml"}

_ANALYSIS_HINTS = (
    "分析",
    "解释",
    "梳理",
    "理解",
    "执行流程",
    "代码结构",
    "路由逻辑",
    "turn loop",
    "workflow",
)

_ACTION_BANS = (
    "修改",
    "修复",
    "实现",
    "重构",
    "优化",
    "删除",
    "写入",
    "patch",
    "运行",
    "测试",
    "部署",
    "安装",
    "modify",
    "fix",
    "implement",
    "refactor",
    "optimize",
    "delete",
    "write",
    "run",
    "test",
    "deploy",
    "install",
)


@dataclass
class ReadPrefetchDecision:
    should_prefetch: bool
    target_file: str | None
    reason: str
    confidence: float
    max_lines: int
    max_chars: int
    signals: list[str] = field(default_factory=list)


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _contains_any(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if phrase.lower() in text:
            return phrase
    return None


def _resolve_project_root(project_root: str | Path) -> Path:
    return Path(project_root).resolve()


def _path_within_root(path: Path, project_root: Path) -> bool:
    try:
        path.relative_to(project_root)
        return True
    except ValueError:
        return False


def _candidate_strings(text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(re.findall(r"`([^`]+)`", text))
    candidates.extend(re.findall(r'"([^"]+)"', text))
    candidates.extend(re.findall(r"'([^']+)'", text))
    path_pattern = (
        r"(?<![\w.-])"
        r"([A-Za-z0-9_.-]+(?:[\\/][A-Za-z0-9_.-]+)+\.(?:py|md|txt|json|yaml|yml|toml))"
        r"(?![\w.-])"
    )
    file_pattern = (
        r"(?<![\w.-])"
        r"([A-Za-z0-9_.-]+\.(?:py|md|txt|json|yaml|yml|toml))"
        r"(?![\w.-])"
    )
    candidates.extend(re.findall(path_pattern, text, flags=re.IGNORECASE))
    candidates.extend(re.findall(file_pattern, text, flags=re.IGNORECASE))
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        item = str(candidate or "").strip().strip("\"'")
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _is_absolute_candidate(candidate: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:[\\/]", candidate)) or candidate.startswith(("/", "\\"))


def _contains_parent_ref(candidate: str) -> bool:
    normalized = candidate.replace("\\", "/")
    return any(part == ".." for part in normalized.split("/"))


def _resolve_explicit_file_candidate(candidate: str, project_root: Path) -> tuple[Path | None, str]:
    raw = str(candidate or "").strip().strip("\"'")
    if not raw:
        return None, "empty_candidate"
    if _is_absolute_candidate(raw) or _contains_parent_ref(raw):
        return None, "unsafe_path"

    normalized = raw.replace("\\", "/")
    relative_candidate = Path(normalized)
    if relative_candidate.suffix.lower() not in _ALLOWED_SUFFIXES:
        return None, "unsupported_extension"

    if len(relative_candidate.parts) > 1:
        target = (project_root / relative_candidate).resolve()
        if not _path_within_root(target, project_root):
            return None, "unsafe_path"
        if not target.is_file():
            return None, "explicit_file_not_found"
        return target, "ok"

    direct_target = (project_root / relative_candidate.name).resolve()
    if direct_target.is_file() and _path_within_root(direct_target, project_root):
        return direct_target, "ok"

    matches = [
        path.resolve()
        for path in project_root.rglob(relative_candidate.name)
        if path.is_file() and _path_within_root(path.resolve(), project_root)
    ]
    if len(matches) == 1:
        return matches[0], "ok"
    if len(matches) > 1:
        return None, "ambiguous_filename"
    return None, "explicit_file_not_found"


def _resolve_explicit_file(query: str, project_root: Path) -> tuple[Path | None, str, str | None]:
    candidates = _candidate_strings(query)
    if not candidates:
        return None, "no_explicit_file", None
    for candidate in candidates:
        target, reason = _resolve_explicit_file_candidate(candidate, project_root)
        if target is not None:
            return target, "ok", candidate
        if reason in {"unsafe_path", "ambiguous_filename"}:
            return None, reason, candidate
    return None, "explicit_file_not_found", candidates[0]


def _analysis_intent(query: str) -> tuple[bool, list[str]]:
    signals: list[str] = []
    matched = _contains_any(query, _ANALYSIS_HINTS)
    if matched:
        signals.append(f"analysis_intent:{matched}")
        return True, signals

    if "看看" in query and ("逻辑" in query or "执行流程" in query):
        signals.append("analysis_intent:看看...逻辑/执行流程")
        return True, signals

    return False, signals


def detect_read_prefetch(
    query: str,
    project_root: str | Path,
    default_max_lines: int = 200,
    default_max_chars: int = 12000,
) -> ReadPrefetchDecision:
    root = _resolve_project_root(project_root)
    normalized = _normalize(query)
    max_lines = max(1, int(default_max_lines or 200))
    max_chars = max(1, int(default_max_chars or 12000))
    signals: list[str] = [f"project_root:{root}"]

    banned = _contains_any(normalized, _ACTION_BANS)
    if banned:
        signals.append(f"blocked_action:{banned}")
        return ReadPrefetchDecision(False, None, "action_request_not_supported", 0.0, max_lines, max_chars, signals)

    has_analysis_intent, intent_signals = _analysis_intent(normalized)
    signals.extend(intent_signals)
    if not has_analysis_intent:
        return ReadPrefetchDecision(False, None, "not_analysis_request", 0.0, max_lines, max_chars, signals)

    target, reason, candidate = _resolve_explicit_file(str(query or ""), root)
    if candidate:
        signals.append(f"file_candidate:{candidate}")

    if reason == "unsafe_path":
        signals.append("unsafe_path")
        return ReadPrefetchDecision(False, None, "unsafe_path", 0.0, max_lines, max_chars, signals)
    if reason == "ambiguous_filename":
        signals.append("ambiguous_filename")
        return ReadPrefetchDecision(False, None, "ambiguous_filename", 0.1, max_lines, max_chars, signals)
    if target is None:
        signals.append(reason)
        return ReadPrefetchDecision(False, None, reason, 0.0, max_lines, max_chars, signals)

    relative_target = target.relative_to(root).as_posix()
    signals.append(f"target_file:{relative_target}")
    signals.append("dry_run_only")
    return ReadPrefetchDecision(
        True,
        target_file=relative_target,
        reason="analysis_single_file_prefetch_candidate",
        confidence=0.88,
        max_lines=max_lines,
        max_chars=max_chars,
        signals=signals,
    )
