# Minimal Experiment Protocol

The minimal experiment ladder prevents open-ended research from jumping straight
to expensive full implementations.

## Ladder

1. Kill test: the smallest test that can falsify the core mechanism.
2. Diagnostic test: a medium test that isolates which component matters.
3. Full benchmark: the complete run only after the first two stages survive.

## Design Checklist

- State the baseline before the new idea.
- Define the falsifiable prediction.
- Name the threshold that would stop the path.
- Name the threshold that would justify scaling the path.
- Log the outcome in the failure ledger even when the result is negative.

## Anti-Patterns

- Starting with a full build because the idea feels promising.
- Measuring only the metric that flatters the idea.
- Ignoring a cheap diagnostic because it is less exciting.
- Moving the goalposts after the first negative result.
