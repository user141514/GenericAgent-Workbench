# Answer Quality Policy

Use this policy when answering roadmap, architecture, capability-gap, and next-step questions about GenericAgent-Workbench.

This guard is intended for planner-path task-local context only. It is not a system prompt, not a classic-executor prompt, and not a general chat overlay.

## Core Rules

1. Before proposing changes, separate four buckets:
   - already active in runtime
   - already integrated but switch-gated
   - infrastructure completed but not yet connected to runtime behavior
   - concept-only / future ideas

2. Do not recommend an existing capability as if it were missing.
   - If it already exists, discuss integration quality, routing quality, prompt bloat, default-off flags, or rollout gaps instead.

3. Do not default to large framework changes when profiler or audit evidence is missing.
   - Prefer measured fixes that reduce `llm_call_count`, `prompt_chars`, `tools_schema_chars`, invalid tool loops, and unnecessary handoffs.

4. When multiple unfinished foundations already exist, prefer:
   - enabling or validating current capabilities
   - connecting existing dry-run infrastructure safely
   - tightening rollback / regression coverage
   - documenting current state clearly
   over introducing new orchestration frameworks.

5. Every roadmap-style answer should explicitly include:
   - current facts
   - judgment
   - next step
   - what not to do

6. External projects such as AutoGen, CrewAI, MemGPT, OpenHands, or Cline may be cited only as reference patterns.
   - They are not default next steps.
   - Do not recommend parallel agents, dynamic agents, or long-term agent memory just because they sound advanced.

7. Memory governance is strict:
   - skills, agents, and tools must not write durable `memory_items`
   - they may only emit runtime metadata, evidence, or pending memory candidates
   - durable memory writes must respect `MemoryWriteGate`

8. Research/code precedence is explicit:
   - user constraints and provided files outrank all other context
   - live tool/search results, official docs, repo files, logs, and test output outrank durable memory and model prior experience
   - if model prior experience conflicts with fresh, authoritative, traceable evidence, follow the evidence and mention the conflict when it matters
   - if sources disagree without a clear winner, state uncertainty instead of blending claims

## Preferred Recommendation Order

1. Fix high-impact, measured bottlenecks already visible in profiler/audit.
2. Improve integration quality of existing features already implemented.
3. Safely connect dry-run foundations that clearly reduce current waste.
4. Only then consider importing new frameworks or expanding agent topology.

## Prompt Entropy Controls

- Keep task facts, repo evidence, search evidence, and test output above generic SOP text.
- Inject at most the smallest useful skill summary by default; do not inject whole skill markdown unless explicitly debugging the skill itself.
- Treat `max_chars` as a hard packet limit, not a per-section hint.
- Prefer deleting or compressing low-priority context over adding another guardrail paragraph.

## Common Anti-Patterns

- Saying “add agent memory” when structured memory exists but is simply not connected yet.
- Saying “use parallel agents” when the real bottleneck is repeated classic executor loops or prompt bloat.
- Saying “adopt AutoGen/OpenHands” before exhausting the current profiler/audit evidence.
- Treating switch-gated features as if they do not exist.
- Treating dry-run policy layers as if they already enforce runtime behavior.
