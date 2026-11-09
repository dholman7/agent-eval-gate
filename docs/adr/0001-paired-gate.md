# 1. Gate on a paired test, not interval overlap

Status: accepted, 2026-11-09

## Context

The gate failed a run only when its 95% Wilson interval sat entirely below the baseline's. Non-overlap of two 95% intervals is a test at roughly α ≈ 0.005, not 0.05, and it pools each run's trials, which throws away the fact that both runs scored the same tasks. Computed with the repo's own `wilson()`, a 58/60 baseline passed any run down to 49/60. The CI job's 12/12 reference baseline passed anything down to 7/12, for an agent that should never miss.

## Decision

- **Pair by task.** For each gated metric, take each task's current rate minus its baseline rate. Rates are exact fractions, so runs with different trial counts still pair.
- **Exact sign-flip test, one-sided.** Under no change, each task's difference is equally likely to have gone either way. The p-value counts sign patterns by dynamic programming over integer sums, so it is exact at any size, and with one trial per task it equals the exact McNemar test.
- **Two conditions to fail:** p < 0.05 and a mean drop of at least 5 points. Significance alone lets a large benchmark fail on a trivial drop; size alone fails on noise.
- **Deterministic runs gate exactly.** When both runs are deterministic, any task that got worse is a regression.
- **Keep `--method overlap`** so the two rules can be compared on the same data.

## Alternatives considered

- **Lower the overlap threshold (e.g., 83% intervals).** Still ignores pairing, and the "right" level depends on n.
- **Two-proportion z-test on pooled trials.** Treats a run's trials as independent, but trials of one task are correlated: a hard task fails all three. Overstates confidence.
- **Paired bootstrap for the decision.** Coarse and seed-dependent with 20 tasks of mostly identical outcomes. Kept for the displayed interval only.
- **Bayesian model of per-task rates.** More informative, but the decision would hinge on a prior, which is hard to defend in a CI gate.

## Consequences

- `aeg power` states what the gate can detect. At 20 tasks and 3 trials, it catches a 20-point drop 87% of the time (overlap: 47%), with ≤2% false alarms. It does not reliably catch 5–10 point drops. That limit is published in the README, not hidden.
- The paired method needs per-trial records in both result files. Summary-only results can still use `--method overlap`.
- Old results gate unchanged. Every stored baseline has trial records.
