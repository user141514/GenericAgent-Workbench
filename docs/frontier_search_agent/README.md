# Frontier Search Agent

Frontier Search Agent is the research-mode design direction for this project.
It keeps natural-language collaboration as the foreground while using auditable
state, evidence, counterclaims, execution traces, metrics, and failure archives
as the background.

Read in this order:

1. [`design_philosophy.md`](design_philosophy.md) - the full design worldview.
2. [`frontier_constitution.md`](frontier_constitution.md) - compact engineering doctrine.
3. [`runtime_mapping.md`](runtime_mapping.md) - current code mapping and next slices.

## Non-Goals

- Do not create a separate agent runtime for this direction yet.
- Do not inject these documents wholesale into the system prompt.
- Do not replace natural-language answers with internal state dumps.
- Do not add multi-agent orchestration until state reliability and execution
  honesty are stable.

## Current Runtime Anchors

- Research workflow gate: `core/quality/research_workflow.py`
- Frontier state snapshot: `core/quality/frontier_state.py`
- Execution honesty gate: `core/quality/execution_honesty.py`
- FastAPI/SSE bridge: `core/api/frontier_bridge.py`
- React state panel: `frontends/react_app/src/FrontierStatePanel.tsx`

