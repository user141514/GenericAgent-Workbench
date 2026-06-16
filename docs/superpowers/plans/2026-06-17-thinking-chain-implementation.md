# Thinking Chain Display Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface DeepSeek reasoning_content as structured thinking_block SSE events, rendered as a collapsible timeline inside each TurnTrace card in the React frontend.

**Architecture:** llmcore.py yields thinking deltas as dicts → agent_loop.py emits structured status events → events.py maps them to `thinking_block` kind → SSE stream to React → ThinkingChain component nested inside TurnTracePanel turn cards.

**Tech Stack:** Python 3, React 18 + TypeScript, Zustand store, Server-Sent Events, CSS

---

### Task 1: Backend — llmcore.py: yield thinking deltas

**Files:**
- Modify: `core/llmcore.py:504-505`

- [ ] **Step 1: Yield thinking delta as dict alongside text**

In `_parse_openai_stream()`, after line 505 (`reasoning_text += delta["reasoning_content"]`), add a yield:

```python
# File: core/llmcore.py, lines 504-507
# BEFORE:
            if delta.get("reasoning_content"):
                reasoning_text += delta["reasoning_content"]
            if delta.get("content"):
                text = delta["content"]; content_text += text; yield text

# AFTER:
            if delta.get("reasoning_content"):
                reasoning_text += delta["reasoning_content"]
                yield {"_thinking_delta": delta["reasoning_content"]}
            if delta.get("content"):
                text = delta["content"]; content_text += text; yield text
```

- [ ] **Step 2: Verify edit**

Check the edit is correct:

```bash
grep -A2 "reasoning_text += delta" core/llmcore.py
```

Expected: shows the `yield {"_thinking_delta": ...}` line between the reasoning_text line and the content check.

- [ ] **Step 3: Commit**

```bash
git add core/llmcore.py
git commit -m "feat: yield thinking deltas as dict from OpenAI stream parser"
```

---

### Task 2: Backend — events.py: add thinking_block event kind

**Files:**
- Modify: `core/protocol/events.py:9-19` (EVENT_KINDS)
- Modify: `core/protocol/events.py:81-83` (from_legacy_dict)

- [ ] **Step 1: Add `thinking_block` to EVENT_KINDS**

```python
# File: core/protocol/events.py, lines 9-19
# AFTER:
EVENT_KINDS = frozenset({
    "chunk",        # incremental streaming text (was {"next": ...})
    "done",         # final response (was {"done": ...})
    "status",       # non-text backend status/progress event
    "turn_start",   # new LLM turn began
    "turn_end",     # LLM turn completed
    "turn_delta",   # delta within a turn (paired with chunk)
    "thinking_block",  # LLM reasoning/thinking content block
    "frontier_state",  # expandable research/audit state snapshot
    "stopped",      # user aborted
    "error",        # backend exception
})
```

- [ ] **Step 2: Update `from_legacy_dict()` to map thinking status events**

```python
# File: core/protocol/events.py, lines 81-83
# BEFORE:
        if item_type == "status":
            kind = "turn_start" if item.get("event_type") == "classic_turn_started" else "status"
            text = str(item.get("message", ""))

# AFTER:
        if item_type == "status":
            event_type = item.get("event_type", "")
            if event_type == "classic_turn_started":
                kind = "turn_start"
            elif event_type in ("thinking_delta", "thinking_blocks"):
                kind = "thinking_block"
                text = str(item.get("message", ""))
            else:
                kind = "status"
                text = str(item.get("message", ""))
```

- [ ] **Step 3: Verify edit**

```bash
grep -B2 -A6 "item_type == .status." core/protocol/events.py
```

Expected: shows the new `event_type` variable and if/elif/else structure.

- [ ] **Step 4: Commit**

```bash
git add core/protocol/events.py
git commit -m "feat: add thinking_block event kind and status mapping"
```

---

### Task 3: Backend — agent_loop.py: emit thinking events

**Files:**
- Modify: `core/agent_loop.py:453-473` (verbose and non-verbose response handling)

- [ ] **Step 1: Update verbose mode to detect and emit thinking deltas**

```python
# File: core/agent_loop.py, lines 453-468
# BEFORE:
                if formatter.is_verbose():
                    _resp = None
                    while True:
                        if _stopped():
                            break
                        try:
                            chunk = next(response_gen)
                            yield chunk
                        except StopIteration as e:
                            _resp = e.value
                            break
                    if _stopped():
                        yield "\n\n[已停止输出]\n"
                        break
                    response = _resp
                    yield "\n\n"

# AFTER:
                if formatter.is_verbose():
                    _resp = None
                    while True:
                        if _stopped():
                            break
                        try:
                            chunk = next(response_gen)
                            if isinstance(chunk, dict) and "_thinking_delta" in chunk:
                                yield from _emit_status(handler, {
                                    "type": "status",
                                    "event_type": "thinking_delta",
                                    "scope": "classic_executor",
                                    "message": chunk["_thinking_delta"],
                                    "classic_turn": turn,
                                })
                            else:
                                yield chunk
                        except StopIteration as e:
                            _resp = e.value
                            break
                    if _stopped():
                        yield "\n\n[已停止输出]\n"
                        break
                    response = _resp
                    yield "\n\n"
```

- [ ] **Step 2: Update non-verbose mode to emit thinking after exhaust**

```python
# File: core/agent_loop.py, lines 469-473
# BEFORE:
                else:
                    response = exhaust(response_gen)
                    cleaned = formatter.clean_content(response.content)
                    if cleaned:
                        yield cleaned + "\n"

# AFTER:
                else:
                    response = exhaust(response_gen)
                    if response.thinking:
                        yield from _emit_status(handler, {
                            "type": "status",
                            "event_type": "thinking_blocks",
                            "scope": "classic_executor",
                            "message": response.thinking,
                            "classic_turn": turn,
                        })
                    cleaned = formatter.clean_content(response.content)
                    if cleaned:
                        yield cleaned + "\n"
```

- [ ] **Step 3: Verify edits**

```bash
grep -A12 "if formatter.is_verbose():" core/agent_loop.py | head -20
grep -A10 "response = exhaust(response_gen)" core/agent_loop.py
```

Expected: verbose mode shows `isinstance(chunk, dict) and "_thinking_delta"` check. Non-verbose mode shows `response.thinking` check before `clean_content`.

- [ ] **Step 4: Commit**

```bash
git add core/agent_loop.py
git commit -m "feat: emit thinking_block events in agent loop (verbose + non-verbose)"
```

---

### Task 4: Frontend — types.ts: add thinking_block kind

**Files:**
- Modify: `frontends/react_app/src/types.ts:1-10`

- [ ] **Step 1: Add `thinking_block` to AgentEventKind**

```typescript
// File: frontends/react_app/src/types.ts, lines 1-10
// AFTER:
export type AgentEventKind =
  | "chunk"
  | "done"
  | "status"
  | "turn_start"
  | "turn_end"
  | "turn_delta"
  | "thinking_block"   // NEW — LLM reasoning/thinking content
  | "frontier_state"
  | "stopped"
  | "error";
```

- [ ] **Step 2: Commit**

```bash
git add frontends/react_app/src/types.ts
git commit -m "feat: add thinking_block to AgentEventKind"
```

---

### Task 5: Frontend — ThinkingChain.tsx: new collapsible component

**Files:**
- Create: `frontends/react_app/src/ThinkingChain.tsx`

- [ ] **Step 1: Write the component**

```tsx
// File: frontends/react_app/src/ThinkingChain.tsx (NEW FILE)
import { useEffect, useState } from "react";

interface ThinkingChainProps {
  steps: string[];
  isLive: boolean; // true = this turn is currently running
}

export function ThinkingChain({ steps, isLive }: ThinkingChainProps) {
  const [collapsed, setCollapsed] = useState(!isLive);

  // Auto-collapse when this turn stops running
  useEffect(() => {
    if (!isLive) setCollapsed(true);
  }, [isLive]);

  if (!steps.length) return null;

  if (collapsed) {
    return (
      <div
        className="thinking-chain thinking-collapsed"
        onClick={() => setCollapsed(false)}
      >
        <span className="thinking-chevron">›</span>
        💭 思考过程 ({steps.length} steps)
      </div>
    );
  }

  return (
    <div className="thinking-chain thinking-expanded">
      <div
        className="thinking-header"
        onClick={() => setCollapsed(true)}
      >
        <span className="thinking-chevron open">›</span>
        💭 思考过程 ({steps.length} steps)
      </div>
      <ol className="thinking-steps">
        {steps.map((text, i) => (
          <li
            key={i}
            className={
              i === steps.length - 1 && isLive ? "thinking-live" : ""
            }
          >
            {text}
          </li>
        ))}
      </ol>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontends/react_app/src/ThinkingChain.tsx
git commit -m "feat: add ThinkingChain collapsible component"
```

---

### Task 6: Frontend — TurnTracePanel.tsx: integrate ThinkingChain

**Files:**
- Modify: `frontends/react_app/src/TurnTracePanel.tsx`

- [ ] **Step 1: Add import and update props**

```tsx
// File: frontends/react_app/src/TurnTracePanel.tsx
// Add import at top:
import { ThinkingChain } from "./ThinkingChain";

// Update TurnTraceListProps:
type TurnTraceListProps = {
  events: AgentEvent[];
  thinkingByTurn?: Map<number, string[]>;  // NEW — optional
};
```

- [ ] **Step 2: Render ThinkingChain inside each turn card**

Replace the existing JSX (lines 14-46) with:

```tsx
export function TurnTraceList({ events, thinkingByTurn }: TurnTraceListProps) {
  const turnSummaries = useMemo(() => buildTurnSummaries(events), [events]);
  if (turnSummaries.length === 0) return null;

  return (
    <div className="turn-list">
      {turnSummaries.map((turn) => {
        const thinkingSteps = thinkingByTurn?.get(turn.turn) || [];
        const isLive = turn.state === "running";
        return (
          <details key={turn.turn} className={`turn-card turn-${turn.state}`}>
            <summary>
              <span className="turn-chevron" aria-hidden="true">
                ›
              </span>
              <span className="turn-title">
                {labelForTurnState(turn.state)} (Turn {turn.turn}) ...
              </span>
            </summary>
            <div className="turn-detail">
              <ThinkingChain steps={thinkingSteps} isLive={isLive} />
              <p>{turn.text || (turn.state === "running" ? "运行中..." : "已完成")}</p>
              <div className="turn-meta">
                <span>{turn.chunks} chunks</span>
                <span>{turn.deltas} updates</span>
                <span>{turn.entries.length} detail lines</span>
              </div>
              {turn.entries.length > 0 && (
                <div className="turn-event-lines">
                  {turn.entries.map((entry, index) => (
                    <div key={`${entry.kind}-${index}`} className="turn-event-line">
                      <span>{entry.label}</span>
                      <p>{entry.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontends/react_app/src/TurnTracePanel.tsx
git commit -m "feat: nest ThinkingChain inside each TurnTrace turn card"
```

---

### Task 7: Frontend — App.tsx: derive thinkingByTurn map

**Files:**
- Modify: `frontends/react_app/src/App.tsx`

- [ ] **Step 1: Add useMemo to derive thinkingByTurn**

Insert after the `latestTraceTurn` useMemo (around line 107):

```tsx
const thinkingByTurn = useMemo(() => {
  const map = new Map<number, string[]>();
  for (const e of events) {
    if (e.kind === "thinking_block" && e.text) {
      const arr = map.get(e.turn) || [];
      arr.push(e.text);
      map.set(e.turn, arr);
    }
  }
  return map;
}, [events]);
```

- [ ] **Step 2: Pass thinkingByTurn to both TurnTraceList usages**

First usage (line ~522, inside message render):

Before:
```tsx
{showTraceHere && <TurnTraceList events={events} />}
```

After:
```tsx
{showTraceHere && <TurnTraceList events={events} thinkingByTurn={thinkingByTurn} />}
```

Second usage (line ~539, inside live trace placeholder):

Before:
```tsx
{hasTurnTrace ? <TurnTraceList events={events} /> : <p>正在分析任务…</p>}
```

After:
```tsx
{hasTurnTrace ? <TurnTraceList events={events} thinkingByTurn={thinkingByTurn} /> : <p>正在分析任务…</p>}
```

- [ ] **Step 3: Commit**

```bash
git add frontends/react_app/src/App.tsx
git commit -m "feat: derive thinkingByTurn map and pass to TurnTraceList"
```

---

### Task 8: Frontend — styles.css: thinking chain styles

**Files:**
- Modify: `frontends/react_app/src/styles.css` (append to end)

- [ ] **Step 1: Append thinking chain CSS**

```css
/* Thinking Chain */
.thinking-chain {
  margin: 6px 0 10px;
  border-radius: 6px;
  border: 1px solid #e0d8cc;
  background: #faf8f5;
  overflow: hidden;
}
.thinking-collapsed {
  padding: 6px 10px;
  cursor: pointer;
  font-size: 13px;
  color: #777068;
}
.thinking-collapsed:hover {
  background: #f0ebe0;
}
.thinking-header {
  padding: 6px 10px;
  cursor: pointer;
  font-size: 13px;
  color: #777068;
  border-bottom: 1px solid #e0d8cc;
  user-select: none;
}
.thinking-chevron {
  display: inline-block;
  margin-right: 4px;
  transition: transform 0.15s;
  font-size: 14px;
}
.thinking-chevron.open {
  transform: rotate(90deg);
}
.thinking-steps {
  margin: 0;
  padding: 8px 10px 8px 28px;
  list-style: decimal;
  font-size: 13px;
  color: #555;
  line-height: 1.6;
}
.thinking-steps li {
  margin-bottom: 5px;
}
.thinking-steps li:last-child {
  margin-bottom: 0;
}
.thinking-live {
  color: #c97754;
}
.thinking-live::after {
  content: "▍";
  animation: think-blink 1s step-end infinite;
}
@keyframes think-blink {
  50% {
    opacity: 0;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontends/react_app/src/styles.css
git commit -m "style: add thinking chain CSS"
```

---

### Task 9: Frontend — Tests: update TurnTracePanel test + add ThinkingChain test

**Files:**
- Modify: `frontends/react_app/src/TurnTracePanel.test.tsx`
- Create: `frontends/react_app/src/ThinkingChain.test.tsx`

- [ ] **Step 1: Update TurnTracePanel.test.tsx for thinkingByTurn prop**

The existing test passes no `thinkingByTurn`, which is fine (optional prop). Add a new test for thinking rendering:

```tsx
// Add to TurnTracePanel.test.tsx after existing describe() block:

import { ThinkingChain } from "./ThinkingChain";

// Add import for ThinkingChain at top too.

describe("TurnTraceList with thinking", () => {
  it("renders thinking chain inside turn cards when thinkingByTurn is provided", () => {
    const thinkingByTurn = new Map<number, string[]>();
    thinkingByTurn.set(1, [
      "Analyzing the codebase structure",
      "Identifying relevant files",
    ]);
    thinkingByTurn.set(2, ["Formulating response"]);

    render(
      <TurnTraceList
        events={[
          event("turn_start", 1),
          event("thinking_block", 1, "Analyzing the codebase structure"),
          event("thinking_block", 1, "Identifying relevant files"),
          event("turn_end", 1),
          event("turn_start", 2),
          event("thinking_block", 2, "Formulating response"),
        ]}
        thinkingByTurn={thinkingByTurn}
      />,
    );

    // Turn 1 card shows thinking collapsed
    expect(screen.getByText("💭 思考过程 (2 steps)")).toBeTruthy();
    // Turn 2 card shows thinking collapsed
    expect(screen.getByText("💭 思考过程 (1 steps)")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Create ThinkingChain.test.tsx**

```tsx
// File: frontends/react_app/src/ThinkingChain.test.tsx (NEW FILE)
// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThinkingChain } from "./ThinkingChain";

describe("ThinkingChain", () => {
  it("renders nothing when steps is empty", () => {
    const { container } = render(
      <ThinkingChain steps={[]} isLive={false} />,
    );
    expect(container.textContent).toBe("");
  });

  it("renders collapsed by default when not live", () => {
    render(
      <ThinkingChain
        steps={["Step 1 text", "Step 2 text"]}
        isLive={false}
      />,
    );
    expect(screen.getByText("💭 思考过程 (2 steps)")).toBeTruthy();
    expect(screen.queryByText("Step 1 text")).toBeNull();
  });

  it("renders expanded when isLive is true", () => {
    render(
      <ThinkingChain
        steps={["Step 1 text", "Step 2 text"]}
        isLive={true}
      />,
    );
    expect(screen.getByText("Step 1 text")).toBeTruthy();
    expect(screen.getByText("Step 2 text")).toBeTruthy();
  });

  it("auto-collapses when isLive changes to false", () => {
    const { rerender } = render(
      <ThinkingChain
        steps={["Step 1"]}
        isLive={true}
      />,
    );
    expect(screen.getByText("Step 1")).toBeTruthy();

    rerender(
      <ThinkingChain
        steps={["Step 1"]}
        isLive={false}
      />,
    );
    // After isLive becomes false, step text should be hidden (collapsed)
    expect(screen.queryByText("Step 1")).toBeNull();
    expect(screen.getByText("💭 思考过程 (1 steps)")).toBeTruthy();
  });

  it("expands on click when collapsed", () => {
    render(
      <ThinkingChain
        steps={["Expand me"]}
        isLive={false}
      />,
    );
    fireEvent.click(screen.getByText("💭 思考过程 (1 steps)"));
    expect(screen.getByText("Expand me")).toBeTruthy();
  });

  it("collapses on header click when expanded", () => {
    render(
      <ThinkingChain
        steps={["Collapse me"]}
        isLive={true}
      />,
    );
    // Click the header to collapse
    const header = screen.getByText("💭 思考过程 (1 steps)");
    fireEvent.click(header);
    expect(screen.queryByText("Collapse me")).toBeNull();
  });

  it("applies thinking-live class to last step when isLive", () => {
    render(
      <ThinkingChain
        steps={["First", "Last"]}
        isLive={true}
      />,
    );
    const steps = document.querySelectorAll(".thinking-steps li");
    expect(steps[0].className).not.toContain("thinking-live");
    expect(steps[1].className).toContain("thinking-live");
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd frontends/react_app && npx vitest run src/ThinkingChain.test.tsx src/TurnTracePanel.test.tsx
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontends/react_app/src/ThinkingChain.test.tsx frontends/react_app/src/TurnTracePanel.test.tsx
git commit -m "test: add ThinkingChain tests + update TurnTracePanel tests"
```

---

### Task 10: Build and verify

**Files:**
- No new files. Verify the full pipeline.

- [ ] **Step 1: Install frontend dependencies if needed**

```bash
cd frontends/react_app && npm install
```

- [ ] **Step 2: Run all frontend tests**

```bash
cd frontends/react_app && npx vitest run
```

Expected: all tests pass (existing + new).

- [ ] **Step 3: Type-check frontend**

```bash
cd frontends/react_app && npx tsc --noEmit
```

Expected: no type errors.

- [ ] **Step 4: Build frontend**

```bash
cd frontends/react_app && npx vite build
```

Expected: clean build, no errors.

- [ ] **Step 5: Verify backend syntax**

```bash
cd /f/GenericAgent-Workbench && python -c "from core.protocol.events import EVENT_KINDS; assert 'thinking_block' in EVENT_KINDS, 'missing thinking_block'; print('EVENT_KINDS OK')"
python -c "from core.llmcore import _parse_openai_stream; print('llmcore OK')"
```

Expected: prints "EVENT_KINDS OK" and "llmcore OK".

- [ ] **Step 6: Commit any final changes**

```bash
git add -A
git commit -m "chore: final build verification after thinking chain implementation"
```

---

## Summary

| Task | What | File(s) |
|------|------|---------|
| 1 | Yield thinking deltas as dicts | `core/llmcore.py` |
| 2 | Add thinking_block event kind + mapping | `core/protocol/events.py` |
| 3 | Emit thinking events in agent loop | `core/agent_loop.py` |
| 4 | Add thinking_block TS type | `types.ts` |
| 5 | Create ThinkingChain component | `ThinkingChain.tsx` (new) |
| 6 | Nest ThinkingChain in TurnTrace cards | `TurnTracePanel.tsx` |
| 7 | Derive thinkingByTurn map in App | `App.tsx` |
| 8 | Add thinking chain styles | `styles.css` |
| 9 | Add/update tests | `ThinkingChain.test.tsx` (new), `TurnTracePanel.test.tsx` |
| 10 | Build and verify | All |
