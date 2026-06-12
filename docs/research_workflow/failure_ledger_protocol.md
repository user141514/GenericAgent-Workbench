# Failure Ledger Protocol

The failure ledger turns failed experiments into reusable research evidence. It
should be used for algorithm innovation, benchmark work, paper claim decisions,
and repeated system optimization failures.

## Required Fields

- Hypothesis: what the attempt expected to prove.
- Observed result: what actually happened, with evidence source when available.
- Failure type: data, objective, implementation, evaluation, scaling, or claim.
- Information bottleneck: what is still unknown.
- Implication: what claim, design path, or experiment is now ruled in or out.
- Next action: the smallest diagnostic that resolves the bottleneck.

## Rules

- Do not treat negative results as waste.
- Do not retry a larger version of the same idea before naming what failed.
- Preserve surprising failures as possible mechanism or benchmark claims.
- Keep the ledger short enough to update during normal work.
