# Canonical Context Pipeline

> Target architecture for context assembly.
> This is the DESIGN. Implementation is a future phase.
> Current state: 5 read paths → Target state: 1 read path.

## Principle

**Every byte of context injected into the LLM must pass through a single, auditable pipeline.**

```
Context Sources           ContextBuilder              Injection Points
─────────────────        ──────────────              ────────────────
L1 (insight)         →                         →    Classic system prompt
L2 (global_mem)      →   ContextBuilder.build() →    OpenAI inputs list
Structured memory    →   (single entry point)   →    Agent instructions
Recent conversation  →                         →
SOP matches          →                         →
Workspace info       →                         →
Uploaded files       →                         →
```

## Pipeline Stages

### Stage 1: Source Readers

Each source type has exactly ONE reader:

| Source | Reader Module | Returns |
|---|---|---|
| L1/L2 markdown | `core/context/memory_reader.py::MemoryReader` | `MemoryBlock` (priority-ordered) |
| Structured memory | `core/context/memory_reader.py::MemoryReader` | `List[EvidenceChunk]` |
| Recent conversation | `core/context/recent_turns.py::build_recent_conversation_block()` | `str` |
| SOP matches | `core/skills/skill_prompt_injector.py::SkillSelector` | `str` |
| Workspace info | `core/context/workspace_probe.py` | `WorkspaceInfo` |
| Uploaded files | `frontends/file_processor.py::build_attachment_prompt()` | `str` |

**Rule:** No other module may read `memory/global_mem_insight.txt`, `memory/global_mem.txt`, or `memory/catalog.sqlite` directly.

### Stage 2: Context Builder

`core/context/context_builder.py::ContextBuilder`

```python
class ContextBuilder:
    """Single entry point for all context assembly."""

    def build(self, *, sources: List[str], max_tokens: int) -> ContextPacket:
        """Build context packet from specified sources.

        Args:
            sources: Which sources to include.
                     Options: "l1_l2", "structured", "recent_turns",
                              "sop", "workspace", "files"
            max_tokens: Hard cap on total context size.

        Returns:
            ContextPacket with ordered blocks, each with role and priority.
        """
        ...
```

### Stage 3: Injection Adapters

Thin adapters that take a `ContextPacket` and inject it into the appropriate LLM interface:

| Adapter | Target |
|---|---|
| `ClassicContextAdapter` | `agent_loop.py::agent_runner_loop()` — builds `messages[0]` system prompt |
| `OpenAIContextAdapter` | `openai_agentmain.py::_run_task_async()` — builds `inputs` list |
| `AgentInstructionAdapter` | Agent `instructions=` parameter |

## ContextPacket Structure

```python
@dataclass
class ContextBlock:
    role: Literal["system", "context", "memory", "conversation", "skills", "files"]
    priority: int  # lower = more important, used for truncation
    content: str
    source: str  # traceability: which reader produced this

@dataclass
class ContextPacket:
    blocks: List[ContextBlock]
    total_chars: int
    truncated: bool  # True if any block was truncated to fit max_tokens
```

## Structural Markers

Each block in the final prompt has a clear structural marker that distinguishes it from user input:

| Role | Marker |
|---|---|
| `system` | `role: system` (API-native) or no prefix (system prompt position) |
| `memory` | `[PROJECT MEMORY]` header |
| `conversation` | `[RECENT CONTEXT]` header |
| `skills` | `[ACTIVE SKILLS]` header |
| `files` | `[ATTACHED FILES]` header |
| `context` | `[WORKSPACE CONTEXT]` header |

**Rule:** No injected context block may use bare `role: user` without a structural marker.

## Enforced Constraints

1. **Single reader rule:** Only `MemoryReader` touches L1/L2 files.
2. **No new context builders:** All context assembly goes through `ContextBuilder.build()`. New injection points extend the adapter, not the pipeline.
3. **No hand-rolled context in openai_agentmain.py:** The 10-item `inputs` list is replaced by `OpenAIContextAdapter.inject(packet, inputs)`.
4. **No assistant-as-fact:** Summary extraction for memory injection is read-only for context purposes. Distillation requires cross-reference.
5. **ContextBuilder is the only main path.** Legacy paths are deprecated, not deleted, until migration is complete.

## Size Budget

| Level | Budget | Enforcement |
|---|---|---|
| Per-block | 2000 chars soft cap | `ContextBuilder` truncates with `...` |
| Per-source | 6000 chars hard cap | `ContextBuilder` slices |
| Total packet | 12000 chars hard cap | `ContextBuilder` drops lowest-priority blocks |
| Per-turn history entry | 500 chars soft cap | `recent_turns.py` truncates |

## Migration Path

1. Build `ContextBuilder` and `MemoryReader` as canonical path (new code, no touch old).
2. Add `--context-runtime` flag gating the new pipeline.
3. Run both paths in parallel (new logs to `temp/context_audit/` for comparison).
4. Once parity confirmed, switch `agentmain.py` and `openai_agentmain.py` to new path.
5. Deprecate old read paths. Keep code for one release cycle.
6. Delete old read paths.

---

*Design: 2026-05-05. Subject to review before Phase 2 implementation.*
