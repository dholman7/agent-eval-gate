"""Compares a run to a stored baseline and fails only on regressions it can tell from noise.

Both runs score the same tasks, so the comparison is paired: each task's rate in the current run
is set against that task's rate in the baseline. A metric regresses when an exact sign-flip test
says a drop this large is unlikely by chance (p < alpha) and the mean drop is at least
`min_effect`. Deterministic runs have no noise, so between two of them any task that got worse is
a regression. `method="overlap"` keeps the older, far less sensitive rule (non-overlapping
intervals) for comparison.
"""

import math
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from agent_eval_gate.results import RunResult, TrialRecord
from agent_eval_gate.stats import Estimate, bootstrap_mean, sign_flip_p

Method = Literal["paired", "overlap"]
ALPHA = 0.05
MIN_EFFECT = 0.05

# Metric name -> whether higher is better.
GATED = {"task_success": True, "bug_detection": True, "false_failure": False}


def _ran(t: TrialRecord) -> bool:
    return not t.load_errors and t.clean_passed + t.clean_failed > 0


# Per-task (numerator, denominator) for each gated metric, matching `results.summarize`. A task
# with a zero denominator has no value for that metric: no bugs to catch, or no suite that ran.
TASK_RATES: dict[str, Callable[[list[TrialRecord]], tuple[int, int]]] = {
    "task_success": lambda ts: (sum(t.success for t in ts), len(ts)),
    "bug_detection": lambda ts: (
        sum(t.kills.get(bug, False) for t in ts for bug in t.bugs),
        sum(len(t.bugs) for t in ts),
    ),
    "false_failure": lambda ts: (
        sum(t.clean_failed > 0 for t in ts if _ran(t)),
        sum(_ran(t) for t in ts),
    ),
}


@dataclass
class Check:
    metric: str
    baseline: Estimate
    current: Estimate
    regressed: bool
    # Mean per-task change, current minus baseline, with a bootstrap interval. Paired only.
    change: Estimate | None = None
    # One-sided p-value for a drop this bad by chance. Paired, non-deterministic runs only.
    p_value: float | None = None


class IncomparableRuns(ValueError):
    pass


def per_task(result: RunResult, metric: str) -> dict[str, Fraction]:
    by_task: dict[str, list[TrialRecord]] = defaultdict(list)
    for t in result.trials:
        by_task[t.task_id].append(t)
    rates = {}
    for task, trials in by_task.items():
        num, den = TASK_RATES[metric](trials)
        if den:
            rates[task] = Fraction(num, den)
    return rates


def paired(
    base: dict[str, Fraction], cur: dict[str, Fraction], higher_is_better: bool
) -> tuple[list[Fraction], float]:
    """Per-task changes (current minus baseline) and the p-value that they're this bad by chance.

    Rates are exact fractions, so scaling by the common denominator gives the integer
    differences the exact test needs, even when the two runs used different trial counts.
    """
    diffs = [cur[t] - base[t] for t in sorted(base.keys() & cur.keys())]
    sign = 1 if higher_is_better else -1
    scale = math.lcm(*(d.denominator for d in diffs)) if diffs else 1
    return diffs, sign_flip_p([int(sign * d * scale) for d in diffs])


def is_regression(
    diffs: list[Fraction], p: float, higher_is_better: bool, alpha: float, min_effect: float
) -> bool:
    """Significant (p < alpha) and large enough to matter (mean drop of at least min_effect)."""
    if not diffs:
        return False
    mean = sum(diffs, Fraction(0)) / len(diffs)
    drop = -mean if higher_is_better else mean
    # Compare as fractions: the float 0.05 is a hair above 1/20 and would let an exact
    # 5-point drop through.
    return p < alpha and drop >= Fraction(str(min_effect))


def compare(
    baseline: RunResult,
    current: RunResult,
    method: Method = "paired",
    alpha: float = ALPHA,
    min_effect: float = MIN_EFFECT,
) -> list[Check]:
    for field in ("benchmark", "split"):
        if getattr(baseline.meta, field) != getattr(current.meta, field):
            raise IncomparableRuns(
                f"{field} differs: baseline {getattr(baseline.meta, field)!r}, "
                f"current {getattr(current.meta, field)!r}"
            )
    if method == "overlap":
        checks = []
        for metric, higher_is_better in GATED.items():
            base: Estimate = getattr(baseline.summary, metric)
            cur: Estimate = getattr(current.summary, metric)
            regressed = cur.high < base.low if higher_is_better else cur.low > base.high
            checks.append(Check(metric, base, cur, regressed))
        return checks

    if not baseline.trials or not current.trials:
        raise IncomparableRuns("the paired method needs per-trial records in both runs")
    base_tasks = {t.task_id for t in baseline.trials}
    cur_tasks = {t.task_id for t in current.trials}
    if base_tasks != cur_tasks:
        raise IncomparableRuns(
            f"task sets differ: only in baseline {sorted(base_tasks - cur_tasks)}, "
            f"only in current {sorted(cur_tasks - base_tasks)}"
        )
    exact = baseline.meta.mode == current.meta.mode == "deterministic"
    checks = []
    for metric, higher_is_better in GATED.items():
        diffs, p = paired(per_task(baseline, metric), per_task(current, metric), higher_is_better)
        if exact:
            sign = 1 if higher_is_better else -1
            regressed = any(sign * d < 0 for d in diffs)
        else:
            regressed = is_regression(diffs, p, higher_is_better, alpha, min_effect)
        checks.append(
            Check(
                metric,
                getattr(baseline.summary, metric),
                getattr(current.summary, metric),
                regressed,
                change=bootstrap_mean([float(d) for d in diffs]),
                p_value=None if exact else p,
            )
        )
    return checks


def _range(e: Estimate) -> str:
    return f"{e.value:.0%} ({e.low:.0%}–{e.high:.0%})"


def _change(e: Estimate | None) -> str:
    if e is None:
        return "–"
    return f"{e.value * 100:+.0f} pts ({e.low * 100:+.0f} to {e.high * 100:+.0f})"


def markdown(
    checks: list[Check],
    method: Method = "paired",
    alpha: float = ALPHA,
    min_effect: float = MIN_EFFECT,
) -> str:
    rows = [
        f"| {c.metric.replace('_', ' ')} | {_range(c.baseline)} | {_range(c.current)} "
        f"| {_change(c.change)} | {'–' if c.p_value is None else f'{c.p_value:.3f}'} "
        f"| {'regressed' if c.regressed else 'ok'} |"
        for c in checks
    ]
    if method == "overlap":
        rule = (
            "Rule: a metric regresses when its interval falls entirely on the bad side of "
            "the baseline's."
        )
    elif all(c.p_value is None for c in checks):
        rule = "Rule: both runs are deterministic, so any task that got worse is a regression."
    else:
        rule = (
            f"Rule: paired by task; a metric regresses when p < {alpha:g} and the mean change is "
            f"at least {min_effect * 100:g} points in the bad direction."
        )
    verdict = "Gate failed." if any(c.regressed for c in checks) else "Gate passed."
    return "\n".join(
        [
            "| Metric | Baseline | Current | Paired change (95% CI) | p | Result |",
            "|---|---|---|---|---|---|",
            *rows,
            "",
            rule,
            "",
            verdict,
            "",
        ]
    )
