"""
Context Builder — pure constructor. Takes typed dataclasses, returns ContextPacket.

NEVER reads files. NEVER reads SQLite. NEVER reads global memory directly.
All memory content arrives via MemoryBundle from MemoryReader.
"""

import time
from dataclasses import dataclass, field

# ── Route budgets ──

_ROUTE_BUDGET: dict[str | None, dict[str, int]] = {
    "chat":            {"workspace": 0,   "project": 0,   "state": 0,   "memory": 0},
    "code":            {"workspace": 100, "project": 100,  "state": 0,   "memory": 1500},
    "review":          {"workspace": 100, "project": 100,  "state": 200, "memory": 1500},
    "research":        {"workspace": 100, "project": 100,  "state": 0,   "memory": 2500},
    "executor":        {"workspace": 150, "project": 150,  "state": 500, "memory": 3000},
    "planner_executor": {"workspace": 150, "project": 150, "state": 500, "memory": 3000},
    None:              {"workspace": 0,   "project": 0,   "state": 0,   "memory": 0},
}

# Truncation order when over budget: volatile → supplementary → state blocks.
# Identity blocks (workspace, project) are never truncated — they are tiny.


@dataclass
class ContextPacket:
    """Assembled context for agent injection."""

    workspace: "WorkspaceSnapshot | None" = None
    project: "ProjectIdentity | None" = None
    runtime: "RuntimeIdentity | None" = None
    current_session: "SessionRecord | None" = None
    last_active_task: "TaskState | None" = None
    active_tasks: list = field(default_factory=list)
    memory_bundle: "MemoryBundle | None" = None
    generated_at: float = 0.0
    total_chars: int = 0
    source_breakdown: dict[str, int] = field(default_factory=dict)
    policy_mode: str = "preview"
    target_route: str | None = None
    max_chars_limit: int = 4000

    def __post_init__(self):
        if self.generated_at == 0.0:
            self.generated_at = time.time()


class ContextBuilder:
    """Pure constructor for ContextPacket.

    Usage:
        builder = ContextBuilder(max_chars=4000, policy_mode="preview")
        packet = builder.build(
            workspace=snap, project=pid, runtime=rt,
            session=rec, memory_bundle=bundle,
            target_route="code",
        )
    """

    def __init__(self, *, max_chars: int = 4000, policy_mode: str = "preview"):
        self._max_chars = max_chars
        self._policy_mode = policy_mode

    # ── Public API ──

    def build(
        self,
        *,
        workspace: "WorkspaceSnapshot | None" = None,
        project: "ProjectIdentity | None" = None,
        runtime: "RuntimeIdentity | None" = None,
        session: "SessionRecord | None" = None,
        last_task: "TaskState | None" = None,
        active_tasks: list | None = None,
        memory_bundle: "MemoryBundle | None" = None,
        target_route: str | None = None,
    ) -> ContextPacket | None:
        """Build a ContextPacket. Returns None when:
        - policy_mode == 'off'
        - target_route is None or 'chat' (no injection for casual conversation)
        """
        if self._policy_mode == "off":
            return None
        if target_route is None or target_route == "chat":
            return None

        budget = _ROUTE_BUDGET.get(target_route, _ROUTE_BUDGET[None])
        workspace_chars = budget.get("workspace", 0)
        project_chars = budget.get("project", 0)
        state_chars = budget.get("state", 0)
        memory_chars = budget.get("memory", 0)

        breakdown: dict[str, int] = {}

        # ── Workspace block (never truncated, small) ──
        ws_text = self._format_workspace(workspace) if workspace and workspace_chars > 0 else ""
        ws_text = ws_text[:workspace_chars] if workspace_chars > 0 else ""
        breakdown["workspace"] = len(ws_text)

        # ── Project block ──
        pr_text = self._format_project(project) if project and project_chars > 0 else ""
        pr_text = pr_text[:project_chars] if project_chars > 0 else ""
        breakdown["project"] = len(pr_text)

        # ── State block ──
        st_text = self._format_state(session, last_task, active_tasks) if state_chars > 0 else ""
        st_text = st_text[:state_chars] if state_chars > 0 else ""
        breakdown["state"] = len(st_text)

        # ── Memory block ──
        mem_text = self._format_memory(memory_bundle, memory_chars) if memory_bundle and memory_chars > 0 else ""
        breakdown["memory"] = len(mem_text)

        total = sum(breakdown.values())

        return ContextPacket(
            workspace=workspace,
            project=project,
            runtime=runtime,
            current_session=session,
            last_active_task=last_task,
            active_tasks=active_tasks or [],
            memory_bundle=memory_bundle,
            generated_at=time.time(),
            total_chars=total,
            source_breakdown=breakdown,
            policy_mode=self._policy_mode,
            target_route=target_route,
            max_chars_limit=self._max_chars,
        )

    def serialize(self, packet: ContextPacket) -> str:
        """Render a ContextPacket to the injection text format."""
        if packet is None:
            return ""

        parts: list[str] = []
        parts.append(
            f"[CONTEXT PACKET — {packet.policy_mode} mode, "
            f"{packet.total_chars} chars, route={packet.target_route}]"
        )

        ws = packet.workspace
        if ws:
            parts.append("\n## Workspace")
            parts.append(f"cwd: {ws.cwd}")
            if ws.git_root:
                parts.append(f"git_root: {ws.git_root}")
            if ws.git_branch:
                parts.append(f"branch: {ws.git_branch}")
            parts.append(f"dirty: {ws.has_uncommitted_changes}")
            if ws.dirty_files:
                parts.append(f"changed: {', '.join(ws.dirty_files[:10])}")

        pr = packet.project
        if pr:
            parts.append("\n## Project")
            parts.append(f"project_id: {pr.project_id}")
            parts.append(f"name: {pr.project_name}")
            parts.append(f"root: {pr.project_root}")
            if pr.key_files:
                parts.append(f"key_files: {', '.join(pr.key_files[:10])}")
            if pr.languages:
                parts.append(f"languages: {', '.join(pr.languages)}")

        rt = packet.runtime
        if rt:
            parts.append("\n## Runtime")
            parts.append(f"session_id: {rt.session_id}")
            parts.append(f"backend: {rt.agent_backend}")

        if packet.current_session:
            s = packet.current_session
            parts.append("\n## Session")
            parts.append(f"tasks: {s.task_count}")
            if s.last_completed_task_id:
                parts.append(f"last_completed: {s.last_completed_task_id}")

        if packet.last_active_task:
            t = packet.last_active_task
            parts.append("\n## Last Task")
            parts.append(f"summary: {t.summary} [{t.status}]")
            if t.exit_reason:
                parts.append(f"exit: {t.exit_reason}")

        if packet.active_tasks:
            parts.append("\n## Active Tasks")
            for t in packet.active_tasks[:5]:
                parts.append(f"- {t.summary} [{t.status}]")

        if packet.memory_bundle and packet.memory_bundle.blocks:
            parts.append("\n## Relevant Memory")
            for b in packet.memory_bundle.blocks:
                src = f"[{b.source} | priority={b.source_priority} | score={b.relevance_score:.2f}]"
                parts.append(f"\n{src}")
                parts.append(b.content)

        parts.append("\n[/CONTEXT PACKET]")
        return "\n".join(parts)

    # ── Format helpers ──

    @staticmethod
    def _format_workspace(ws: "WorkspaceSnapshot") -> str:
        lines = [f"cwd: {ws.cwd}"]
        if ws.git_root:
            lines.append(f"git_root: {ws.git_root}")
            if ws.git_branch:
                lines.append(f"branch: {ws.git_branch}")
            lines.append(f"dirty: {ws.has_uncommitted_changes}")
            if ws.dirty_files:
                lines.append(f"changed: {', '.join(ws.dirty_files[:10])}")
        return "\n".join(lines)

    @staticmethod
    def _format_project(pr: "ProjectIdentity") -> str:
        lines = [
            f"project_id: {pr.project_id}",
            f"name: {pr.project_name}",
            f"root: {pr.project_root}",
        ]
        if pr.key_files:
            lines.append(f"key_files: {', '.join(pr.key_files[:10])}")
        if pr.languages:
            lines.append(f"languages: {', '.join(pr.languages)}")
        return "\n".join(lines)

    @staticmethod
    def _format_state(
        session: "SessionRecord | None",
        last_task: "TaskState | None",
        active_tasks: list | None,
    ) -> str:
        lines: list[str] = []
        if session:
            lines.append(f"session: {session.session_id} ({session.task_count} tasks)")
            if session.current_active_task_id:
                lines.append(f"active_task: {session.current_active_task_id}")
        if last_task:
            lines.append(f"last_task: {last_task.summary} [{last_task.status}]")
        if active_tasks:
            for t in active_tasks[:5]:
                lines.append(f"  - {t.summary} [{t.status}]")
        return "\n".join(lines)

    @staticmethod
    def _format_memory(bundle: "MemoryBundle", max_chars: int) -> str:
        if not bundle or not bundle.blocks:
            return ""
        parts: list[str] = []
        budget = max_chars
        for b in bundle.blocks:
            if budget <= 0:
                break
            header = f"[{b.source} | priority={b.source_priority} | score={b.relevance_score:.2f}]"
            parts.append(header)
            budget -= len(header) + 1
            content = b.content
            if len(content) > budget:
                content = content[:budget] + "…"
            parts.append(content)
            budget -= len(content) + 1
        return "\n".join(parts)
