# Turn Status Event Contract

## Problem

`planner_executor` / outer orchestrator turn and classic GenericAgent executor turn are two different counters.

- Outer turn: the OpenAI Agents orchestration loop.
- Classic turn: the inner `agent_runner_loop()` inside the classic executor.

If the UI only displays the outer turn, the screen can stay at `LLM Running (Turn 1)` even when the classic executor has already advanced to turn 16.

## Event Model

Classic executor emits a structured queue item:

```json
{
  "type": "status",
  "event_type": "classic_turn_started",
  "scope": "classic_executor",
  "agent_name": "classic_executor",
  "classic_turn": 3,
  "max_turns": 80,
  "message": "Classic executor running turn 3"
}
```

## Rules

- `classic_turn_started` is a status event, not assistant content.
- It must not be appended to the final assistant message body.
- It must not be parsed back out of assistant text with regex.
- Frontends should track nested state:
  - outer orchestrator/planner turn
  - inner classic executor turn

## UI Guidance

Recommended status text:

- `Planner turn 1 · Classic executor turn 3`
- or, when no outer turn is available:
  - `Classic executor turn 3`

## Current Runtime Scope

This event is intended for observability only.

- No prompt change
- No model change
- No tool behavior change
- No stop/max_turn policy change

## Profiler

Classic loop also records:

- `classic_executor_turn_started`

Metadata:

- `classic_turn`
- `max_turns`
- `scope`
- `agent_name`
