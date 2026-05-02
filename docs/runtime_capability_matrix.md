# Runtime Capability Matrix

This matrix separates what is already active in runtime from what is only a switch, only infrastructure, or still a concept.

## A. Active In Main Flow

| Capability | Status | Key Files | Affects | Notes |
|---|---|---|---|---|
| RouterRules quick routing | active | `core/router_rules.py`, `core/openai_agentmain.py` | routing | Cheap chat/executor pre-routing before LLM routing. |
| task_router / chat_specialist / planner_executor | active | `core/openai_agentmain.py` | routing, execution | Orchestrator agent graph is live. |
| classic GenericAgent executor handoff | active | `core/openai_agentmain.py`, `core/agentmain.py`, `core/agent_loop.py` | execution, tools | Planner can hand work to classic executor. |
| RuntimeProfiler | active when enabled | `core/runtime/profiler.py`, `core/openai_agentmain.py`, `core/agent_loop.py` | observability | Real spans/events are emitted in live runs. |
| LLM audit | active | `core/runtime/llm_cache.py`, `core/llmcore.py` | observability | Real LLM call audit with prompt/response stats. |
| tool schema slimming | active when enabled | `core/tools/schema_selector.py`, `core/agentmain.py` | prompt, tools | Slims classic executor tool schema. |
| direct answer | active when enabled | `core/runtime/direct_answer.py`, `core/agent_loop.py` | execution | Can skip final classic LLM summarization for narrow read tasks. |
| read shortcut | active when enabled | `core/runtime/read_shortcut.py`, `core/agentmain.py` | routing, execution | Narrow file-read shortcut before classic executor loop. |
| orchestrator skip planner follow-up | active with read shortcut | `core/openai_agentmain.py`, `core/agentmain.py` | routing, execution | Lets orchestrator end run when shortcut already produced final answer. |
| Optional SOP planner injection | active when enabled | `core/skills/skill_prompt_injector.py`, `core/openai_agentmain.py` | prompt | Only planner task-local context, not system prompt. |
| State-Aware Answer Quality Guard | active when enabled | `core/quality/answer_quality_context.py`, `core/openai_agentmain.py` | prompt, observability | Injected only on planner-path roadmap / architecture questions; not added to system prompt or classic executor. |
| phase-aware skill selector | active | `core/skills/skill_selector.py`, `core/skills/skill_phase.py` | prompt selection | Skills are filtered by phase before injection. |
| Memory Write Gate | active in memory store | `core/memory/write_gate.py`, `core/memory/store.py` | memory | Durable memory writes are now source-gated. |

## B. Integrated But Switch-Gated

| Capability | Switch | Key Files | Affects | Notes |
|---|---|---|---|---|
| Optional SOP planner injection | `GENERIC_AGENT_SKILL_SOP=1` | `core/skills/skill_prompt_injector.py` | prompt | Default off. |
| Answer Quality Guard | `GENERIC_AGENT_ANSWER_QUALITY=1` | `core/quality/answer_quality_context.py` | prompt | Default off. |
| tool schema slimming | `GENERIC_AGENT_SLIM_TOOLS=1` | `core/tools/schema_selector.py` | prompt, tools | Default off or environment-controlled. |
| direct answer | `GENERIC_AGENT_DIRECT_ANSWER=1` | `core/runtime/direct_answer.py` | execution | Narrow task class only. |
| read shortcut | `GENERIC_AGENT_READ_SHORTCUT=1` | `core/runtime/read_shortcut.py` | execution | Narrow task class only. |
| early stop | `GENERIC_AGENT_EARLY_STOP=1` | `core/runtime/early_stop.py` | execution | Classic executor only. |
| profiler export | `GENERIC_AGENT_PROFILE=1` | `core/runtime/profiler.py` | observability | Default off. |

## C. Infrastructure Done, Not Yet Changing Runtime Behavior

| Capability | Status | Key Files | Affects | Notes |
|---|---|---|---|---|
| SkillEffects | dry-run only | `core/skills/skill_effects.py` | tools, context, routing | Metadata exists, not applied. |
| ExecutionPolicy merge | dry-run only | `core/runtime/execution_policy.py` | tools, context, routing | Policy is generated, not enforced. |
| SkillActivation policy preview | dry-run only | `core/skills/skill_activation.py`, `core/openai_agentmain.py` | observability | Logged, not enforced. |
| structured memory store | infra only | `core/memory/store.py`, `core/memory/schema.sql` | memory | SQLite ledger exists but does not drive prompt retrieval yet. |
| evidence chunk FTS index | infra only | `core/memory/indexer.py`, `core/memory/store.py` | memory, observability | Searchable evidence exists but is not main prompt context source. |
| LLM cache get/set | infra only | `core/runtime/llm_cache.py` | llm | Audit is active; cache reuse is not enabled. |
| discovered skills layer | infra only | `core/skills/skill_discovery.py`, `core/skills/skill_parser.py` | prompt, governance | Metadata discovery exists; discovered skills are not auto-enabled. |

## D. Concept-Only / Future Directions

| Capability | Status | Key Files | Affects | Notes |
|---|---|---|---|---|
| tool-backed skill runtime (level 3+) | concept | n/a | tools, execution | Not implemented as a live runtime. |
| workflow skill runtime | concept | n/a | routing, execution | Not implemented. |
| reviewer-phase injection | concept | n/a | prompt | Phase infra exists, reviewer injection does not. |
| dynamic agent spawning | concept | n/a | routing, execution | No live runtime integration. |
| parallel agent execution | concept | n/a | routing, execution | Not active in main flow. |
| trust-policy marketplace | concept | n/a | governance | No runtime enforcement path. |

## Recommended Reading Order

1. `core/openai_agentmain.py`
2. `core/agentmain.py`
3. `core/agent_loop.py`
4. `core/runtime/*`
5. `core/skills/*`
6. `core/memory/*`
