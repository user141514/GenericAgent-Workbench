# Frontier Runtime Mapping

This document maps the Frontier Constitution to the current codebase. It keeps
the philosophy out of the default prompt while making the implementation path
auditable.

Status labels:

- `implemented`: active runtime behavior exists.
- `partial`: active behavior exists, but coverage or enforcement is limited.
- `documented`: design doctrine exists, but no runtime enforcement yet.
- `future`: intentionally deferred.

## Mapping Table

| Constitution principle | Current carrier | Status | Notes / next implementation |
|---|---|---:|---|
| Natural language foreground, state background | `core/quality/frontier_state.py`, `core/api/frontier_bridge.py`, `frontends/react_app/src/FrontierStatePanel.tsx` | partial | State is delivered as a side-channel SSE event and rendered in a collapsed panel. Next: add a short state-delta summary below each relevant answer. |
| AI-native search, not human imitation | `docs/frontier_search_agent/design_philosophy.md`, `docs/research_workflow/strategy_lenses.md` | documented | Keep this as design doctrine, not prompt bloat. Next: turn only the smallest useful pieces into scorers/operators. |
| Move the frontier one step | `core/quality/frontier_state.py` | partial | Snapshot contains intent/evidence/strategy/synthesis/confidence. Next: add a deterministic `state_delta_summary` only after deciding exact UI behavior. |
| Few candidates with selection pressure | `CANDIDATE_OPERATORS` in `core/quality/frontier_state.py` | partial | Operators exist but are still coarse. Next: require selected candidates to include bottleneck, verifier, and handoff. |
| Metric governance | `core/quality/research_workflow.py`, `tests/evaluation/research_eval_runner.py` | partial | Research workflow scorer checks minimal experiment and evidence precedence. Next: add metric failure-mode fields before building a metric archive. |
| Counterevidence before strong claims | `score_research_workflow_response()` in `core/quality/research_workflow.py`; `synthesis_state.warnings` in `core/quality/frontier_state.py` | partial | Strong-claim warnings are deterministic. Next: expose clearer BSA-style labels only after false-positive review. |
| Evidence status is part of the claim | `core/quality/execution_honesty.py`, `core/quality/research_workflow.py` | partial | Execution Honesty tracks response claims and evidence status; research workflow checks evidence/hypothesis split. Next: improve Chinese phrase coverage without mojibake regressions. |
| Execution claims require state delta | `core/quality/execution_honesty.py`, OpenAI bridge metadata | implemented | Hard gate blocks unsupported state-transition claims. Next: keep tightening OpenAI bridge so generic tool success does not prove unrelated quant/causal claims. |
| Versions must not collapse | `REQUIRED_AUDIT_GATES` and scoring flags in `core/quality/research_workflow.py` | partial | Missing version map is detected for research/audit contexts. Next: add a small version-map artifact shape before making this a hard gate. |
| Failure is an asset | `docs/research_workflow/failure_ledger_protocol.md`, `frontier_state.synthesis_state`, `confidence_state.next_verification` | documented | Failure ledger exists as protocol. Next: define minimal failure archive storage and only write failures that change future behavior. |
| Cheap evaluator before full evaluator | `docs/research_workflow/minimal_experiment_protocol.md`, `REQUIRED_SECTIONS` in `core/quality/research_workflow.py` | partial | Minimal experiment ladder is scored. Next: surface kill-test requirement more explicitly in Research Mode. |
| No prompt entropy without runtime value | `build_research_workflow_context()` in `core/quality/research_workflow.py` | partial | Context is capped and only injected for matching tasks. Next: keep doctrine docs out of always-on system prompts; add tests when new lenses are introduced. |

## Implementation Policy

New Frontier features should follow this order:

1. Add or update a constitution/mapping entry.
2. Add a small deterministic test for the behavior.
3. Implement the smallest runtime hook or UI affordance.
4. Verify it does not trigger on ordinary chat, simple code fixes, or read-only tasks.
5. Only then consider prompt/context changes.

This order prevents the project from drifting toward high-entropy prompting or
parallel runtime sprawl.

## Near-Term Candidate Slices

### Slice A: State Delta Summary

Goal: show a compact line such as:

```text
State updated: 1 candidate added, 1 counterclaim required, next handoff prepared.
```

Constraint: do not require the main answer to include YAML or internal logs.

### Slice B: BSA Labels

Goal: map warning flags to stable bad-strategy IDs such as:

```text
BSA-002 Premature Synthesis
BSA-004 Version Collapse
BSA-005 Single-Evidence Mechanism Claim
```

Constraint: keep labels advisory until false-positive rate is measured.

### Slice C: Failure Archive Minimum

Goal: write only reusable failures:

```text
failure_type
trigger
prevention_rule
source_turn
next_check
```

Constraint: do not archive ordinary mistakes that do not change future behavior.

### Slice D: Metric Governance Fields

Goal: attach metric risk to research candidates:

```text
proxy_metric
goodhart_risk
anti_metric
kill_condition
```

Constraint: do not introduce a full metric archive before these fields are used
in at least one evaluation workflow.

