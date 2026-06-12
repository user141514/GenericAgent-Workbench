# Strategy Lenses

This note records the compressed lenses used by the research workflow gate. It
is a maintenance artifact, not a prompt source. Runtime injection should use
only the compact contract in `core/quality/research_workflow.py`.

## Strategy Kernel

A research strategy must name three things:

- Diagnosis: the real bottleneck or constraint.
- Guiding policy: the choice that rules out tempting but weak paths.
- Coherent action: the next steps that reinforce the same diagnosis.

Bad strategy signals:

- Slogans without a bottleneck.
- Tool lists without a hard choice.
- Big implementation before a falsifiable test.
- Ignoring a strong baseline or contrary evidence.

## System Dynamics Lens

Use this lens when progress is shaped by accumulated state, delayed feedback,
or repeated loops.

- Stock: what accumulates, such as unresolved hypotheses or technical debt.
- Flow: what changes the stock, such as experiments, reviews, or refactors.
- Feedback: what signal changes future behavior.
- Delay: where the system learns too late.
- Leverage point: the smallest intervention that changes the loop.

## Evidence Precedence

When model prior and current evidence conflict, prefer:

1. Explicit user constraints and current repo/files/logs/tests/search evidence.
2. Durable memory, summaries, and prior project artifacts.
3. General model experience.

Responses should label verified facts, assumptions, and hypotheses separately.
