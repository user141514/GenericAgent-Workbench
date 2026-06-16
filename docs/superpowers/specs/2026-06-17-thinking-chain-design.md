# Thinking Chain Display Optimization — Design Doc

**Date**: 2026-06-17
**Status**: Draft
**Scope**: Frontend + Backend

---

## 1. Problem

DeepSeek LLM emits native `{"type": "thinking", "thinking": "..."}` content blocks during response generation. Currently:

- **LLM client** (`llmcore.py`): reasoning_content is collected but NOT yielded during streaming — only final text is yielded.
- **agent_loop.py**: `response.thinking` is available on the MockResponse object but never emitted to the frontend.
- **Frontend**: thinking content is either missing or mixed into regular text with no visual distinction.

Users cannot see the model's reasoning process, losing transparency and trust.

## 2. Design

### 2.1 Data Flow

```
DeepSeek API SSE stream
  delta.reasoning_content  ─→  llmcore.py yields {"_thinking_delta": text}
  delta.content            ─→  llmcore.py yields "text" (as before)

agent_loop.py
  chunk is dict with _thinking_delta  ─→  emit thinking_block event via SSE
  chunk is str                        ─→  emit chunk event (as before)

Frontend
  thinking_block events  ─→  store collects per turn
                          ─→  ThinkingChain component renders
  chunk/text events       ─→  existing flow (MarkdownMessage)
```

### 2.2 Backend Changes

#### A. `core/llmcore.py` — `_parse_openai_stream()`

Yield thinking deltas as structured dicts alongside text strings:

```python
# Current (line 504-507):
if delta.get("reasoning_content"):
    reasoning_text += delta["reasoning_content"]
if delta.get("content"):
    text = delta["content"]; content_text += text; yield text

# New:
if delta.get("reasoning_content"):
    reasoning_text += delta["reasoning_content"]
    yield {"_thinking_delta": delta["reasoning_content"]}
if delta.get("content"):
    text = delta["content"]; content_text += text; yield text
```

Consumer code already handles this: `agent_loop.py` line 459 `chunk = next(response_gen)` — then check `isinstance(chunk, dict)` to route.

#### B. `core/agent_loop.py` — `agent_runner_loop()`

**Verbose mode** (line 453-467): detect thinking dicts inline during streaming:

```python
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
```

DeepSeek emits `reasoning_content` deltas BEFORE `content` deltas, so thinking_block events arrive at the frontend first, then text chunks — matching the desired UX.

**Non-verbose mode** (line 469-473): `exhaust()` throws away yielded values, but `response.thinking` is preserved in the StopIteration return value. Emit it after exhaust:

```python
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

Note: in non-verbose mode, the full thinking text is emitted as a single `thinking_blocks` event (not streamed per-delta). The frontend treats both `thinking_delta` and `thinking_blocks` events identically: concatenate by turn.

#### C. `core/protocol/events.py`

Add `"thinking_block"` to `EVENT_KINDS`. Update `from_legacy_dict()` to recognize `thinking_delta` and `thinking_blocks` status events:

```python
# In from_legacy_dict(), inside the item_type == "status" branch:
if item_type == "status":
    event_type = item.get("event_type", "")
    if event_type == "classic_turn_started":
        kind = "turn_start"
    elif event_type in ("thinking_delta", "thinking_blocks"):
        kind = "thinking_block"
        text = str(item.get("message", ""))
    else:
        kind = "status"
    # ...
```

### 2.3 Frontend Changes

#### A. `src/types.ts`

```typescript
export type AgentEventKind =
  | "chunk"
  | "done"
  | "status"
  | "turn_start"
  | "turn_end"
  | "turn_delta"
  | "thinking_block"   // NEW
  | "frontier_state"
  | "stopped"
  | "error";
```

#### B. `src/store.ts` — `applyAgentEvent()`

`thinking_block` events pass through `events[]` array without modifying `messages[]`. The `ThinkingChain` component derives thinking blocks from `events[]` per turn — no store changes needed for the thinking data model. Event accumulation in the existing `events: [...state.events, event].slice(-80)` handles thinking blocks automatically.

#### C. `src/ThinkingChain.tsx` — NEW FILE

```tsx
interface ThinkingBlock {
  text: string;
  turn: number;
}

interface ThinkingChainProps {
  blocks: ThinkingBlock[];
  streaming: boolean;
}

function ThinkingChain({ blocks, streaming }: ThinkingChainProps) {
  const [collapsed, setCollapsed] = useState(!streaming);

  // Auto-collapse when streaming ends (assistant reply arrives)
  useEffect(() => {
    if (!streaming) setCollapsed(true);
  }, [streaming]);

  if (!blocks.length) return null;
  if (collapsed) {
    return (
      <div className="thinking-chain thinking-collapsed" onClick={() => setCollapsed(false)}>
        <span className="thinking-chevron">›</span>
        💭 思考过程 ({blocks.length} steps)
      </div>
    );
  }
  return (
    <div className="thinking-chain thinking-expanded">
      <div className="thinking-header" onClick={() => setCollapsed(true)}>
        <span className="thinking-chevron open">›</span>
        💭 思考过程 ({blocks.length} steps)
      </div>
      <ol className="thinking-steps">
        {blocks.map((block, i) => (
          <li key={i} className={i === blocks.length - 1 && streaming ? "thinking-live" : ""}>
            {block.text}
          </li>
        ))}
      </ol>
    </div>
  );
}
```

#### D. `src/App.tsx` — Integration

Extract thinking blocks from events per turn and render `<ThinkingChain>` above the assistant message:

```tsx
// Derive thinking blocks for the current trace message
const thinkingBlocks = useMemo(() => {
  return events
    .filter(e => e.kind === "thinking_block" && e.turn === latestTraceTurn)
    .map(e => ({ text: e.text, turn: e.turn }));
}, [events, latestTraceTurn]);
```

Render above the TurnTraceList:

```tsx
{showTraceHere && (
  <>
    <ThinkingChain blocks={thinkingBlocks} streaming={status === "running"} />
    <TurnTraceList events={events} />
  </>
)}
```

#### E. `src/styles.css` — Thinking Chain Styles

```css
.thinking-chain {
  margin: 8px 0;
  border-radius: 6px;
  border: 1px solid #e0d8cc;
  background: #faf8f5;
  overflow: hidden;
}
.thinking-collapsed {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  color: #777068;
}
.thinking-collapsed:hover { background: #f0ebe0; }
.thinking-header {
  padding: 8px 12px;
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
.thinking-chevron.open { transform: rotate(90deg); }
.thinking-steps {
  margin: 0;
  padding: 10px 12px 10px 32px;
  list-style: decimal;
  font-size: 13px;
  color: #555;
  line-height: 1.6;
}
.thinking-steps li { margin-bottom: 6px; }
.thinking-steps li:last-child { margin-bottom: 0; }
.thinking-live { color: #c97754; }
.thinking-live::after {
  content: "▍";
  animation: blink 1s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }
```

### 2.4 Component Tree (after change)

```
Message (assistant)
├── ThinkingChain          ← NEW (thinking_block events, per turn)
│   ├── collapsed: "💭 思考过程 (N steps)"
│   └── expanded:
│       ├── Step 1: "..."
│       ├── Step 2: "..."
│       └── Step N: "..." (blinking cursor if streaming)
├── TurnTraceList          ← existing
└── MarkdownMessage        ← existing (final answer text)
```

### 2.5 State Transitions

```
idle → [user sends message] → running
  → thinking_block events arrive (streaming)
    → ThinkingChain: expanded, last step blinking
  → chunk events arrive (text)
    → MarkdownMessage: streams text
    → ThinkingChain: still expanded
  → done event
    → ThinkingChain: auto-collapse to "💭 思考过程 (N steps)"
    → MarkdownMessage: final text
```

## 3. Testing Plan

### Backend Tests
- Verify `_parse_openai_stream()` yields `{"_thinking_delta": ...}` for reasoning_content deltas
- Verify agent_loop emits thinking_block events in correct turn order
- Verify events.from_legacy_dict() correctly maps status→thinking_block

### Frontend Tests
- `ThinkingChain.test.tsx`: renders collapsed/expanded, handles empty blocks, handles streaming
- `store.test.ts`: thinking_block events pass through events array
- Manual: send prompt requiring reasoning, verify thinking chain appears

## 4. Future Extensions

- **Streaming thinking**: current design yields thinking deltas during streaming, but the frontend receives them as discrete events (not per-character). For true per-character streaming of thinking text, add a `thinking_chunk` event type.
- **Thinking metadata**: add confidence scores, tool-call annotations to thinking blocks
- **Thinking retention**: persist thinking across history restore
