# State Driven Thinking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make gagent use a state-driven control kernel for complex reasoning tasks without exposing internal state JSON in final replies.

**Architecture:** Add a focused `core.quality.state_driven_thinking` module that owns the schema, action vocabulary, injection triggers, and compact prompt block. Export it through `core.quality`, then inject it into both classic and OpenAI runtime context paths alongside the existing quality guards.

**Tech Stack:** Python 3.12, pytest, existing `core.quality` context injection patterns, packaged npm backend sync.

## Global Constraints

- Keep final user replies natural; do not force visible control JSON.
- Do not change conversation history file format.
- Do not rewrite the agent loop into a new state machine in this pass.
- Keep package and C盘 global npm backend synchronized after verification.

---

### Task 1: State-Driven Thinking Kernel

**Files:**
- Create: `F:\GenericAgent-Workbench\core\quality\state_driven_thinking.py`
- Modify: `F:\GenericAgent-Workbench\core\quality\__init__.py`
- Test: `F:\GenericAgent-Workbench\tests\unit\test_state_driven_thinking.py`

**Interfaces:**
- Produces: `state_driven_thinking_enabled() -> bool`
- Produces: `should_inject_state_driven_thinking(user_input: str, route_target: str | None = None) -> bool`
- Produces: `build_state_driven_thinking_context(user_input: str, route_target: str | None = None, max_chars: int = 3200) -> dict`

- [ ] Write failing tests for trigger behavior, schema/action vocabulary, and compact prompt content.
- [ ] Run `python -m pytest tests\unit\test_state_driven_thinking.py -v` and confirm failure because the module does not exist.
- [ ] Implement the module with conservative triggers and no external dependencies.
- [ ] Export functions in `core\quality\__init__.py`.
- [ ] Re-run `python -m pytest tests\unit\test_state_driven_thinking.py -v`.

### Task 2: Runtime Injection

**Files:**
- Modify: `F:\GenericAgent-Workbench\core\agentmain.py`
- Modify: `F:\GenericAgent-Workbench\core\openai_agentmain.py`
- Test: `F:\GenericAgent-Workbench\tests\unit\test_state_driven_thinking.py`

**Interfaces:**
- Consumes: `build_state_driven_thinking_context(...)`
- Produces: quality context blocks that include `### State-Driven Thinking Core` only for matched complex requests.

- [ ] Add tests proving classic context helpers and OpenAI context assembly can import the new quality functions.
- [ ] Inject the state-driven block next to existing answer-quality/problem-framing/research-workflow blocks.
- [ ] Keep simple read-style requests unmodified.
- [ ] Run targeted Python tests.

### Task 3: Package Sync And Verification

**Files:**
- Copy root changes into `F:\GenericAgent-Workbench\packages\gagent-desktop\backend`
- Copy package backend changes into `C:\Users\14579\AppData\Roaming\npm\node_modules\gagent-desktop\backend`

- [ ] Run targeted unit tests.
- [ ] Run package prepublish check.
- [ ] Run C盘 npm package dry-run.
- [ ] Verify package/global backend hash parity for touched files.
