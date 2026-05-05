# Problem Framing Layer and Clarification Gate

## Overview

This document describes two complementary mechanisms that improve agent task understanding and reduce unnecessary user interrogations in GenericAgent-Multi:

1. **Problem Framing Layer** (`core/quality/problem_framing.py`) — classifies user input into task frames as a public understanding constraint.
2. **Clarification Gate** (`core/runtime/clarification_gate.py`) — restricts `ask_user` calls to only truly necessary cases.

## Design Philosophy

**Default: Do not ask the user.** When the agent encounters ambiguity, it should:

1. Make minimal, reversible, low-risk assumptions.
2. Examine existing state (files, logs, config) rather than interrogating the user.
3. Narrow scope based on explicit words, then broaden only if evidence demands it.
4. Only ask the user in truly unavoidable situations.

## Problem Framing Layer

### What it is

A public task-understanding constraint injected into the system prompt. It is NOT hidden chain-of-thought reasoning. It tells the model how to approach the problem without asking unnecessary clarification questions.

### What it does

- Classifies user input into frames: `improvement`, `architecture`, `roadmap`, `understanding`, `implementation`, `ai_capability`, `general`.
- Injects a compact framing hint that constrains the model's behavior.
- Does NOT force the model to output the classification or the framing rules.

### Trigger rules

The layer activates when user input contains keywords from these categories:

| Category | Chinese Keywords | English Keywords |
|----------|-----------------|------------------|
| Improvement | 优化, 改进, 提升, 性能, 瓶颈, 效率 | optimize, improve, performance, bottleneck |
| Architecture | 架构, 重构, 设计, 解耦, 模式 | architecture, refactor, design, decouple |
| Roadmap | 下一步, 规划, 路线图, 优先级 | roadmap, plan, next step, priority |
| Understanding | 理解, 分析, 审查, 诊断, 调试 | understand, analyze, review, diagnose, debug |
| AI Capability | 人工智能, 智能体, 模型, RAG, token | AI, agent, model, reasoning, prompt, llm |

**Exclusions:** Simple read operations ("读取 README 第一行"), greetings ("你好"), and plain implementation requests do NOT trigger framing.

### Environment variable

```
GENERIC_AGENT_PROBLEM_FRAMING=1
```

Default: **off**.

## Clarification Gate

### What it is

A runtime gate that intercepts `ask_user` tool calls and decides whether the question is truly necessary. When a question is denied, it returns a `fallback_instruction` so the model can continue with assumptions — it does NOT fail the turn.

### ClarificationDecision

```
ClarificationDecision:
  allowed: bool          # whether ask_user is permitted
  reason: str            # which rule triggered
  risk_level: str        # none / low / medium / high / critical
  confidence_gap: float  # for equiprobable-candidate cases
  fallback_instruction: str  # what to tell the model when denied
  signals: list[str]     # which rule patterns matched
```

### Allow rules (when ask_user IS permitted)

| Rule | Condition | Risk Level | Example |
|------|-----------|------------|---------|
| **A** | Safety/irreversible keyword detected AND target is missing | high | "删除这个目录" (no target in context) |
| **B1** | Vague action phrase ("帮我改一下") without target object | medium | "帮我改一下" (no target file) |
| **B2** | Ambiguous pronoun ("这个") without following target noun | medium | "这个怎么处理" (no antecedent) |
| **C** | Two or more candidates with score gap < 0.15 AND divergent actions | medium | Candidate A (0.51, rewrite) vs B (0.49, small_patch) |
| **E** | Cost difference ratio > 5x between options | medium | Cost ratio 10x between deployment methods |
| **F** | Privacy or permission check required by context | high | `requires_privacy_check` in context |

### Deny rules (when ask_user is BLOCKED)

| Rule | Condition | Example |
|------|-----------|---------|
| **A (with target)** | Danger keyword matched BUT target is already present | "删除临时文件" (target_file = "/tmp/cache") |
| **D** | Probing question about user preference | "你想优化前端还是后端？" |
| **Default** | No trigger condition met | General clarification attempts |

### Fallback behavior

When denied, the gate returns a tool result with:
- `status: "BLOCKED"`
- `gate: "clarification"`
- `reason`: which rule blocked it
- `fallback_instruction`: what the model should do instead
- A `next_prompt` instructing the model to continue with assumptions

The model continues execution — it does NOT exit or fail.

### Profiler events

Three events are recorded (when profiler is active):

| Event | When |
|-------|------|
| `clarification_requested` | Every time ask_user is attempted |
| `clarification_allowed` | When the gate permits the question |
| `clarification_denied` | When the gate blocks the question |

Each event carries metadata: `reason`, `risk_level`, `signals`, `question_chars`, `user_input_preview` (max 300 chars).

### Environment variable

```
GENERIC_AGENT_CLARIFICATION_GATE=1
```

Default: **off**.

## Integration Points

### ask_user tool

`GenericAgentHandler.do_ask_user()` in `core/ga.py` checks the clarification gate before calling `ask_user()`. The gate is only active when `GENERIC_AGENT_CLARIFICATION_GATE=1`. When disabled, `ask_user` works as before.

### User input flow

`agent_runner_loop()` in `core/agent_loop.py` stores the user input on the handler via `handler._last_user_input`, making it available for gate decisions.

### Problem framing injection

The problem framing context can be injected into the system prompt by the caller (e.g., in `agentmain.py` or `openai_agentmain.py`), similar to how `answer_quality_context` is used. It is NOT automatically injected — the caller checks `should_inject_problem_framing()` and includes the block when appropriate.

## Why This Fits GenericAgent-Multi

1. **No new agent required.** Both mechanisms work within the existing GenericAgentHandler architecture.
2. **No model config changes.** The gate operates at the tool dispatch level.
3. **Environment-gated.** Both features are off by default via env vars.
4. **Backward compatible.** When env vars are not set, behavior is unchanged.
5. **Complements existing quality layers.** Works alongside `answer_quality_context`, `execution_policy`, `early_stop`, and `direct_answer`.

## What NOT to do

- Do NOT enable by default.
- Do NOT intercept all user input — framing only triggers on matched patterns.
- Do NOT make the model output chain-of-thought.
- Do NOT modify `read_shortcut`, `read_prefetch`, `llm_cache`, or `memory write gate`.
- Do NOT make denied `ask_user` fail — always return a `fallback_instruction`.
- Do NOT add external dependencies.
