# Memory System Workflow — Full Architecture

> Phase M0-M8 complete. All components ready, default: preview mode (no runtime change).

## 1. Canonical Context Pipeline (Main Flow)

```
                         ┌──────────────────────────┐
                         │      User Query           │
                         └────────────┬─────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         ▼                            ▼                            ▼
┌─────────────────┐   ┌──────────────────────────┐   ┌──────────────────────┐
│ Conversation    │   │   Uploaded Files          │   │   Route Detection    │
│ Pool / Recent   │   │   (file_processor.py)     │   │   (RouterRules)      │
│ Turns (M4)      │   │                          │   │   → chat/code/review │
│                 │   │                          │   │   /research/executor │
│ recent_turns.py │   │                          │   │                      │
└────────┬────────┘   └────────────┬─────────────┘   └──────────┬───────────┘
         │                         │                            │
         │  [RECENT CONTEXT]       │  [ATTACHED FILES]         │  route_target
         │                         │                            │
         ▼                         ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTEXT BUILDER  (M4)                               │
│                     core/context/context_builder.py                          │
│                                                                             │
│  Inputs:  workspace  project  runtime  session  recent_turns  working_mem   │
│  Output:  ContextPacket { blocks[], total_chars, source_breakdown }         │
│  Rule:    NEVER reads files/SQLite. All data pre-assembled by readers.      │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    │  ContextPacket
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐   ┌────────────────────────┐   ┌──────────────────────────┐
│ Classic Adapter │   │ OpenAI Adapter  (M5)    │   │ Handoff Bridge    (M6)  │
│ (stub)          │   │ core/context/           │   │ agentmain.py             │
│                 │   │ adapters.py             │   │ _build_recent_context()  │
│                 │   │                         │   │ → delegates to canonical │
│                 │   │ OpenAIContextAdapter    │   │   recent_turns module    │
└────────┬────────┘   └───────────┬────────────┘   └────────────┬─────────────┘
         │                        │                              │
         │  system prompt         │  inputs list                 │  user_input
         │  messages[0]           │  (with markers)              │  prepended
         │                        │                              │
         ▼                        ▼                              ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              AGENT  (execution)                               │
│                                                                              │
│  Classic: agent_runner_loop()           OpenAI: Runner.run_streamed()         │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
                                    │  tool_calls + results
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐   ┌────────────────────────┐   ┌──────────────────────────┐
│ Tool Event      │   │ Change Classifier (M7) │   │ Assistant Output          │
│ Ledger (M7)     │   │                        │   │ (summary / text)          │
│                 │   │ core/context/          │   │                           │
│ core/context/   │   │ change_classifier.py   │   │ ⚠ NOT execution evidence  │
│ tool_event_     │   │                        │   │ ⚠ NOT trusted fact        │
│ ledger.py       │   │ proposed vs executed   │   │                           │
│                 │   │                        │   │                           │
│ executed facts  │   │ verify_against_ledger()│   │                           │
│ ONLY evidence   │   │                        │   │                           │
└────────┬────────┘   └───────────┬────────────┘   └────────────┬──────────────┘
         │                        │                              │
         │  tool events           │  change records              │  summary text
         │                        │                              │
         └────────────────────────┼──────────────────────────────┘
                                  │
                                  │  cross-reference (M8)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         DISTILLATION  (M8)                                    │
│                     core/memory/distillation.py                              │
│                                                                              │
│  verify_distillation_candidate(ledger, classifier)                           │
│       │                                                                      │
│       ├─ tool_cross_reference: { verified, matched_files, unmatched }       │
│       │                                                                      │
│       ▼                                                                      │
│  write_distillation_candidate()                                              │
│       │                                                                      │
│       ├─ is_proposed=True  → REFUSED (never write proposals)                │
│       ├─ mode=preview      → temp/distillation_previews/*.json              │
│       │                       { verification_status, tool_cross_reference } │
│       └─ mode=write        → memory/history_memory_inbox.md                 │
│                               (only if verified & executed)                  │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                    │
                                    │  inbox entry
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         LONG-TERM MEMORY                                      │
│                                                                              │
│  L1: memory/global_mem_insight.txt    ←─ file_patch (agent tool)             │
│  L2: memory/global_mem.txt            ←─ file_patch (agent tool)             │
│  L3: memory/*.md (SOPs)               ←─ file_write (agent tool)             │
│  Structured: memory/catalog.sqlite    ←─ maintenance.archive_inbox()         │
│                                                                              │
│  ALL read via: MemoryReader  (M3)                                            │
│       core/context/memory_reader.py                                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 2. Memory Read Path (Before → After)

```
BEFORE (5 paths):
  ┌──────────────────┐
  │ legacy_global.py │──→ read_legacy_l1_l2()        ──→ Classic get_system_prompt()
  │  (DEPRECATED)    │──→ build_legacy_memory_block() ──→ Classic get_global_memory()
  └──────────────────┘
  ┌──────────────┐
  │ reader.py     │──→ read_global_memory()          ──→ OpenAI _build_context_runtime()
  │ (DEPRECATED)  │
  └──────────────┘
  ┌──────────────────┐
  │ maintenance.py   │──→ build_scoped_memory_context() ──→ maintenance tools
  └──────────────────┘

AFTER (1 path):
  ┌──────────────────────────────┐
  │ core/context/memory_reader.py│
  │ MemoryReader  (CANONICAL)    │
  │                              │
  │ .read_global_memory()        │──→ {l1, l2}
  │ .read_global_memory_blocks() │──→ [MemoryBlock]
  │ .read_structured_memory()    │──→ [MemoryBlock]
  │ .read_session_state()        │──→ SessionRecord
  │ .scoped_query()              │──→ MemoryBundle
  │                              │
  │ + standalone wrappers:       │
  │   read_global_memory()       │──→ matches reader.py API
  │   search_structured_memory() │──→ matches reader.py API
  │   read_working_memory()      │──→ matches reader.py API
  │   build_memory_source_report()│── matches reader.py API
  └──────────────────────────────┘
```

## 3. Context Injection (OpenAI Path: Before → After)

```
BEFORE M5 (11 bare role:user):
  inputs[0]  {"role":"user", "content": working_memory}        ← no marker
  inputs[1]  {"role":"user", "content": context_packet}         ← no marker
  inputs[2]  {"role":"user", "content": recent_block}           ← no marker
  inputs[3]  {"role":"user", "content": legacy_memory}          ← no marker
  inputs[4]  {"role":"user", "content": route_hint}             ← no marker
  inputs[5]  {"role":"user", "content": answer_quality}         ← no marker
  inputs[6]  {"role":"user", "content": sop_context}            ← no marker
  inputs[7]  {"role":"user", "content": prefetch}               ← no marker
  inputs[8]  {"role":"user", "content": clarification}          ← no marker
  inputs[9]  {"role":"user", "content": skill_policy}           ← no marker
  inputs[10] {"role":"user", "content": raw_query}              ← no marker

AFTER M5 (with structural markers):
  inputs[0..n]   input_items (history, as-is)
  inputs[n+1]    [WORKING MEMORY]      ← structural marker
  inputs[n+2]    [CONTEXT PACKET]      ← structural marker
  inputs[n+3]    [RECENT CONTEXT]      ← structural marker
  inputs[n+4]    [PROJECT MEMORY]      ← structural marker
  inputs[n+5]    [ROUTER HINT]         ← structural marker
  inputs[n+6]    [ANSWER QUALITY]      ← structural marker
  inputs[n+7]    [ACTIVE SKILLS]       ← structural marker
  inputs[n+8]    [PREFETCH CONTENT]    ← structural marker
  inputs[n+9]    [CONTEXT NOTE]        ← structural marker
  inputs[LAST]   raw_query             ← user input, no marker
```

## 4. Execution → Memory Cycle

```
┌─────────────────────────────────────────────────────────────────┐
│                        TURN LOOP                                │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ LLM Call │───→│ Tool Dispatch│───→│ Tool Event Recorded  │  │
│  │          │    │ (agent_loop) │    │ (M7 ledger hook)     │  │
│  └──────────┘    └──────────────┘    └──────────┬───────────┘  │
│       ↑                                         │              │
│       │                                         ▼              │
│       │                              ┌──────────────────────┐  │
│       │                              │ Change Classified    │  │
│       │                              │ proposed vs executed │  │
│       │                              └──────────┬───────────┘  │
│       │                                         │              │
│       │         ┌───────────────────────────────┘              │
│       │         │                                              │
│       │         ▼                                              │
│       │  ┌────────────────┐                                    │
│       │  │ Next Prompt    │                                    │
│       │  │ + Working Mem  │                                    │
│       │  │ + L1/L2 (10th) │                                    │
│       │  └────────┬───────┘                                    │
│       │           │                                            │
│       └───────────┘                                            │
└─────────────────────────────────────────────────────────────────┘

Between sessions:
  ┌────────────────┐    ┌──────────────────┐    ┌─────────────────┐
  │ self.history   │───→│ _build_recent_   │───→│ [RECENT CONTEXT]│
  │ (Classic)      │    │ context()  (M6)  │    │ injected into    │
  │                │    │ → canonical      │    │ next user_input  │
  └────────────────┘    └──────────────────┘    └─────────────────┘

  ┌────────────────┐    ┌──────────────────┐    ┌─────────────────┐
  │ input_items    │───→│ build_recent_    │───→│ [RECENT CONTEXT]│
  │ (OpenAI)       │    │ conversation_    │    │ in inputs list  │
  │                │    │ block()          │    │                 │
  └────────────────┘    └──────────────────┘    └─────────────────┘
```

## 5. Module Map by Phase

```
core/context/
├── memory_reader.py      M3: canonical read layer + standalone wrappers
├── context_builder.py    M4: assembles ContextPacket from all sources
├── adapters.py           M5: OpenAIContextAdapter + ClassicContextAdapter
├── recent_turns.py       M6: unified ambiguous detection + recent context
├── tool_event_ledger.py  M7: executed fact evidence (ONLY evidence)
├── change_classifier.py  M7: proposed vs executed separation
├── workspace_probe.py    (pre-existing)
├── project_identity.py   (pre-existing)
├── runtime_identity.py   (pre-existing)
├── session_store.py      (pre-existing)
└── session_dump.py       (pre-existing)

core/memory/
├── reader.py             M3: DEPRECATED → delegates to canonical
├── legacy_global.py      M3: DEPRECATED → replaced by MemoryReader
├── distillation.py       M8: verified distillation + cross-reference
├── store.py              (unchanged)
├── maintenance.py        (unchanged)
├── write_gate.py          (unchanged)
└── types.py              (unchanged)

core/
├── agent_loop.py         M7: ledger init + recording hook
├── agentmain.py          M6: Classic handoff bridge
├── openai_agentmain.py   M5: adapter gate
└── ga.py                 (unchanged for memory pipeline)
```

## 6. Data Flow Summary

```
READ PATH:
  L1/L2 files ──→ MemoryReader (M3) ──→ ContextBuilder (M4) ──→ Adapters (M5/M6) ──→ Agent

EXECUTION PATH:
  Agent ──→ ToolEventLedger (M7) ──→ ChangeClassifier (M7)
       ──→ Distillation.verify() (M8) ──→ Preview JSON
       ──→ write mode? ──→ history_memory_inbox.md ──→ maintenance ──→ catalog.sqlite

BRIDGE PATH:
  Classic agentmain.py ──→ canonical recent_turns (M6) ──→ unified [RECENT CONTEXT]
  OpenAI agentmain.py  ──→ canonical recent_turns (M6) ──→ unified [RECENT CONTEXT]
```

## 7. Governance

| What | Status |
|------|--------|
| Default mode | preview (no runtime change) |
| Old read paths | DEPRECATED, delegates to canonical |
| No new runtime injection | Enforced by architecture tests (9/9) |
| No duplicate L1/L2 reads | Enforced by `test_no_new_direct_l1_l2_reads` |
| No bare role:user injection | Enforced by `test_no_new_openai_context_injection_points` |
| Env gates | `GA_CONTEXT_RUNTIME_MODE`, `GA_TOOL_EVENT_LEDGER`, `GA_OPENAI_DISTILLATION`, `GENERIC_AGENT_RECENT_TURNS` |
