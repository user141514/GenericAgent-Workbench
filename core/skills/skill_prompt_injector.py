from __future__ import annotations

import os

from .skill_phase import normalize_skill_phase
from .skill_registry import SkillRegistry
from .skill_selector import SkillSelector


SKILL_SOP_ENV_VAR = "GENERIC_AGENT_SKILL_SOP"
_HEADER = (
    "### Optional SOP\n"
    "The following task-specific SOPs may help. Use them only when relevant. "
    "Do not follow them if they conflict with explicit user instructions or project constraints."
)
_TRUNCATION_MARKER = "\n\n[truncated]"


def _truncate_text(text: str, max_chars: int) -> str:
    limit = max(int(max_chars or 0), 1)
    if len(text) <= limit:
        return text
    if limit <= len(_TRUNCATION_MARKER):
        return text[:limit]
    keep = limit - len(_TRUNCATION_MARKER)
    return text[:keep].rstrip() + _TRUNCATION_MARKER


def skill_sop_enabled() -> bool:
    return str(os.environ.get(SKILL_SOP_ENV_VAR, "0")).strip().lower() in {"1", "true", "yes", "on"}


def build_optional_sop_context(
    user_input: str,
    registry: SkillRegistry | None = None,
    selector: SkillSelector | None = None,
    max_skills: int = 2,
    max_chars_per_skill: int = 1800,
    max_total_chars: int = 3500,
    phase: str = "planner",
) -> dict:
    normalized_phase = normalize_skill_phase(phase)
    empty = {
        "block": "",
        "selected_skills": [],
        "skill_matches": [],
        "chars": 0,
        "phase": normalized_phase,
    }
    try:
        registry = registry or SkillRegistry()
        selector = selector or SkillSelector(registry)
    except Exception:
        return empty

    try:
        selected_matches = selector.select_skill_matches_for_task(
            user_input=user_input,
            max_skills=max_skills,
            phase=normalized_phase,
        )
    except Exception:
        return empty

    if not selected_matches:
        return empty

    header = _truncate_text(_HEADER, max_total_chars)
    chosen: list[str] = []
    chosen_matches: list[dict] = []
    current = header

    for match in selected_matches[: max(0, int(max_skills))]:
        name = match.name
        try:
            skill_text = registry.load_skill_text(name, max_chars=max_chars_per_skill).strip()
        except Exception:
            continue
        if not skill_text:
            continue

        block = f"[Skill: {name}]\n{skill_text}"
        candidate = f"{current}\n\n{block}"
        match_dict = {
            "name": match.name,
            "category": match.category,
            "applies_to": list(match.applies_to),
            "phase": match.phase,
            "score": float(match.score),
            "reasons": list(match.reasons),
            "matched_triggers": list(match.matched_triggers),
        }
        if len(candidate) <= max_total_chars:
            chosen.append(name)
            chosen_matches.append(match_dict)
            current = candidate
            continue

        remaining = max_total_chars - len(current) - 2
        if remaining <= len(f"[Skill: {name}]\n"):
            continue
        trimmed = _truncate_text(block, remaining)
        if not trimmed.strip():
            continue
        chosen.append(name)
        chosen_matches.append(match_dict)
        current = f"{current}\n\n{trimmed}"
        break

    if not chosen:
        return empty
    return {
        "block": current,
        "selected_skills": chosen,
        "skill_matches": chosen_matches,
        "chars": len(current),
        "phase": normalized_phase,
    }


def build_optional_sop_block(
    user_input: str,
    registry: SkillRegistry | None = None,
    selector: SkillSelector | None = None,
    max_skills: int = 2,
    max_chars_per_skill: int = 1800,
    max_total_chars: int = 3500,
    phase: str = "planner",
) -> str:
    return str(
        build_optional_sop_context(
            user_input=user_input,
            registry=registry,
            selector=selector,
            max_skills=max_skills,
            max_chars_per_skill=max_chars_per_skill,
            max_total_chars=max_total_chars,
            phase=phase,
        ).get("block")
        or ""
    )
